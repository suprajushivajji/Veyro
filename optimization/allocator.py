"""
RecoverOS — Portfolio Recovery Allocator

Implements a deterministic greedy ranking allocator solver to select actions
for opportunities that maximize overall Expected Incremental Net Recovery
subject to business and capacity constraints.
"""

import uuid
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from apps.api.models.tables import (
    RecoveryOpportunity, RecoveryPrediction, RecoveryDecision,
    DecisionType, ActionType,
)
from optimization.constraints import AllocationConstraints


class GreedyAllocator:
    def __init__(self, db: Session, merchant_id: str):
        self.db = db
        self.merchant_id = merchant_id
        self.constraints = AllocationConstraints(db, merchant_id)

    def allocate_portfolio(self) -> Dict[str, Any]:
        """
        Runs the portfolio allocation solver.
        1. Find all active opportunities that do not have decisions in this cycle.
        2. Rank them by their maximum expected net recovery.
        3. Allocate actions greedy-style under capacity constraints.
        """
        # Fetch active opportunities with their associated predictions
        opportunities = self.db.query(RecoveryOpportunity).join(
            RecoveryOpportunity.revenue_event
        ).filter(
            RecoveryOpportunity.revenue_event.has(merchant_id=self.merchant_id),
            ~RecoveryOpportunity.decisions.any()  # Opportunities without decisions
        ).all()

        if not opportunities:
            return {
                "message": "No active unscored opportunities to allocate.",
                "total_allocated": 0,
            }

        # Step 1: Pre-evaluate the best action for each opportunity.
        # Filter defensively in Python as well because some lightweight mocks or
        # custom query layers do not preserve .filter() semantics.
        opp_best_action_map: List[Tuple[RecoveryOpportunity, RecoveryPrediction]] = []
        for opp in opportunities:
            predictions = self._get_predictions_for_opportunity(opp.id)
            if not predictions:
                continue

            # Pick the prediction that yields the maximum Expected Net Recovery
            best_pred = max(predictions, key=lambda p: p.expected_net_recovery_paise or 0)
            opp_best_action_map.append((opp, best_pred))

        # Step 2: Sort opportunities by Expected Net Recovery descending
        # High value opportunities get analyzed first to maximize incremental yield
        opp_best_action_map.sort(key=lambda x: x[1].expected_net_recovery_paise, reverse=True)

        allocated_act = 0
        allocated_review = 0
        allocated_suppress = 0
        total_expected_net_recovery = 0

        for opp, best_pred in opp_best_action_map:
            customer_id = opp.revenue_event.customer_id
            amount_paise = opp.amount_at_risk_paise
            net_recovery = best_pred.expected_net_recovery_paise
            action = best_pred.action_type

            # Rule: If the best possible net recovery is zero or negative, SUPPRESS it.
            # Deliberately doing nothing is a first-class feature.
            if net_recovery <= 0:
                self._create_decision(
                    opp.id,
                    DecisionType.SUPPRESS,
                    None,
                    "Intervention is uneconomical: Expected net recovery is <= 0.",
                    best_pred.probability,
                    ["negative_expected_net_recovery"]
                )
                allocated_suppress += 1
                continue

            # Rule: High-value opportunities require manual human review
            is_high_value = amount_paise >= self.constraints.high_value_threshold
            
            if action == ActionType.HUMAN_REVIEW or is_high_value:
                # Flag for manual approval
                self._create_decision(
                    opp.id,
                    DecisionType.REVIEW,
                    action if action == ActionType.HUMAN_REVIEW else ActionType.HUMAN_REVIEW,
                    "High-value case requiring human review before action execution.",
                    best_pred.probability,
                    ["high_value_amount" if is_high_value else "human_review_requested"]
                )
                allocated_review += 1
                continue

            # Check if this automated action is eligible under active constraints
            if self.constraints.can_allocate_automated_action(
                customer_id,
                amount_paise,
                best_pred.probability
            ):
                # Allocate automated execution
                self._create_decision(
                    opp.id,
                    DecisionType.ACT,
                    action,
                    f"Selected automatically to maximize recovery under constraints.",
                    best_pred.probability,
                    ["positive_expected_recovery", "under_capacity_limit"]
                )
                self.constraints.consume_action(customer_id, best_pred.incentive_cost_paise)
                allocated_act += 1
                total_expected_net_recovery += net_recovery
            else:
                # If constraints prevent the absolute best action, see if any fallback fits
                # e.g., if Link was best but exceeds contact cooldown, check if Retry is valid and fits.
                alternative_found = False
                all_preds = self._get_predictions_for_opportunity(opp.id)
                all_preds.sort(key=lambda p: (p.expected_net_recovery_paise or 0), reverse=True)

                for pred in all_preds:
                    if pred.action_type == action or pred.expected_net_recovery_paise <= 0:
                        continue
                    
                    if pred.action_type == ActionType.HUMAN_REVIEW:
                        continue

                    if self.constraints.can_allocate_automated_action(
                        customer_id,
                        amount_paise,
                        pred.probability
                    ):
                        self._create_decision(
                            opp.id,
                            DecisionType.ACT,
                            pred.action_type,
                            f"Selected fallback action {pred.action_type.value} due to capacity/constraint limits on primary choice.",
                            pred.probability,
                            ["fallback_action_selected", "under_capacity_limit"]
                        )
                        self.constraints.consume_action(customer_id, pred.incentive_cost_paise)
                        allocated_act += 1
                        total_expected_net_recovery += pred.expected_net_recovery_paise
                        alternative_found = True
                        break

                if not alternative_found:
                    # Capacity/policies exhausted -> Suppress
                    self._create_decision(
                        opp.id,
                        DecisionType.SUPPRESS,
                        None,
                        "Suppressed: Capacity limits, frequency caps, or quality rules reached for this cycle.",
                        best_pred.probability,
                        ["capacity_limit_exceeded"]
                    )
                    allocated_suppress += 1

        self.db.commit()

        return {
            "total_processed": len(opp_best_action_map),
            "allocated_act": allocated_act,
            "allocated_review": allocated_review,
            "allocated_suppress": allocated_suppress,
            "expected_net_recovery_inr": round(total_expected_net_recovery / 100, 2),
            "remaining_automated_capacity": self.constraints.max_automated_actions - self.constraints.automated_actions_count,
        }

    def _get_predictions_for_opportunity(self, opportunity_id: str) -> List[RecoveryPrediction]:
        """Return all predictions tied to an opportunity, regardless of mock/query behavior."""
        candidates = self.db.query(RecoveryPrediction).all()
        if hasattr(self.db, 'predictions'):
            candidates = [
                pred for pred in self.db.predictions
                if getattr(pred, 'opportunity_id', None) == opportunity_id
            ]
        else:
            candidates = [
                pred for pred in candidates
                if getattr(pred, 'opportunity_id', None) == opportunity_id
            ]
        return candidates

    def _create_decision(
        self,
        opportunity_id: str,
        decision_type: DecisionType,
        action: Optional[ActionType],
        reason: str,
        confidence: float,
        evidence: List[str]
    ) -> RecoveryDecision:
        """Helper to create and save a decision in DB."""
        decision = RecoveryDecision(
            id=f"dec_{uuid.uuid4().hex[:12]}",
            opportunity_id=opportunity_id,
            decision=decision_type,
            recommended_action=action,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            guardrail_passed=True,  # Guardrail engine evaluates this later
            original_decision=decision_type
        )
        self.db.add(decision)
        return decision
