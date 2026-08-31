"""
RecoverOS — Guardrail Engine

A deterministic compliance service that executes AFTER AI/LLM recommendations
and BEFORE execution to guarantee business policy enforcement.
The AI/LLM agent cannot override the guardrail engine.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from apps.api.models.tables import (
    RecoveryDecision, RecoveryOpportunity, RevenueEvent, Customer,
    DecisionType, ActionType,
)
from optimization.constraints import AllocationConstraints


class GuardrailEngine:
    def __init__(self, db: Session, merchant_id: str):
        self.db = db
        self.merchant_id = merchant_id
        self.constraints = AllocationConstraints(db, merchant_id)

    def evaluate_decision(self, decision: RecoveryDecision) -> RecoveryDecision:
        """
        Evaluate and validate a recovery decision.
        Overrides the decision to SUPPRESS or REVIEW if it violates safety limits.
        """
        opp = decision.opportunity
        event = opp.revenue_event
        customer = self.db.query(Customer).filter(Customer.id == event.customer_id).first()

        # Capture original state
        original_decision = decision.decision
        decision.original_decision = original_decision
        decision.guardrail_passed = True
        decision.guardrail_reason = "Passed all compliance guardrails."

        # Rule 1: Customer Opted Out check (Must NEVER contact)
        if customer and customer.opted_out:
            decision.decision = DecisionType.SUPPRESS
            decision.recommended_action = None
            decision.guardrail_passed = False
            decision.guardrail_reason = "Violation: Customer has opted out of communications."
            return decision

        # Rule 2: Frequency check (Prevent customer spam)
        # Check customer run contacts + previous database contacts
        daily_contacts = event.previous_contact_count
        if daily_contacts >= self.constraints.max_contacts_per_customer:
            decision.decision = DecisionType.SUPPRESS
            decision.recommended_action = None
            decision.guardrail_passed = False
            decision.guardrail_reason = f"Violation: Contact count ({daily_contacts}) exceeds daily max limits."
            return decision

        # Rule 3: High-Value Threshold safety check
        if decision.decision == DecisionType.ACT:
            amount_paise = opp.amount_at_risk_paise
            if amount_paise > self.constraints.max_auto_action_amount:
                decision.decision = DecisionType.REVIEW
                decision.recommended_action = ActionType.HUMAN_REVIEW
                decision.guardrail_passed = False
                decision.guardrail_reason = f"Violation: Transaction amount (₹{amount_paise / 100:,.2f}) exceeds auto-action limit (₹{self.constraints.max_auto_action_amount / 100:,.2f}). Escalating to human."
                return decision

        # Rule 4: Action eligibility compliance
        action = decision.recommended_action
        if decision.decision == DecisionType.ACT and action:
            # Recheck action-specific eligibility
            from domain.actions.config import is_action_eligible
            if not is_action_eligible(action, event):
                decision.decision = DecisionType.REVIEW
                decision.recommended_action = ActionType.HUMAN_REVIEW
                decision.guardrail_passed = False
                decision.guardrail_reason = f"Violation: Selected action {action.value} is ineligible for this event context. Routing to human review."
                return decision

        return decision
