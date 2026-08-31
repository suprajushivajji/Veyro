"""
RecoverOS — Opportunity Scoring Engine

Computes Expected Gross Recovery and Expected Net Recovery for each
eligible action of a RecoveryOpportunity. All currency values are in paise.
"""

import uuid
from typing import List
from sqlalchemy.orm import Session

from apps.api.models.tables import (
    RevenueEvent, RecoveryOpportunity, RecoveryPrediction,
    ActionType,
)
from domain.actions.config import ACTION_COSTS, get_eligible_actions
from ml.models.probability_model import RecoveryProbabilityModel


def score_opportunity_actions(
    db: Session,
    opportunity: RecoveryOpportunity,
    event: RevenueEvent,
    model: RecoveryProbabilityModel,
) -> List[RecoveryPrediction]:
    """
    Compute probability and net recovery score for all eligible actions of an opportunity.
    Saves predictions to the database.
    """
    eligible_actions = get_eligible_actions(event)
    predictions = []

    # Get model version metadata
    model_version = "heuristics_v1.0"
    if model.model is not None:
        model_version = "ml_random_forest_v1.0"

    for action in eligible_actions:
        # P(recovery | event, action)
        prob = model.predict_probability(event, action)

        # ─── 1. Expected Gross Recovery ───────────────────────────
        amount_at_risk = opportunity.amount_at_risk_paise
        expected_gross = int(amount_at_risk * prob)

        # ─── 2. Operational Cost ─────────────────────────────────
        action_cost = ACTION_COSTS.get(action, 0)

        # ─── 3. Incentive Cost (Placeholder for discounts) ────────
        # For now, default to 0. Can be configured later.
        incentive_cost = 0

        # ─── 4. Fatigue Penalty ──────────────────────────────────
        # Formula: Fatigue Risk * Amount at Risk * 0.05
        # Fatigue is more expensive for high-fatigue methods like recovery links
        fatigue_risk = opportunity.fatigue_risk or 0.0
        fatigue_multiplier = 0.05 if action == ActionType.SEND_RECOVERY_LINK else 0.02
        fatigue_penalty = int(fatigue_risk * amount_at_risk * fatigue_multiplier)

        # ─── 5. Expected Net Recovery ─────────────────────────────
        expected_net = expected_gross - action_cost - incentive_cost - fatigue_penalty

        # Save prediction
        prediction = RecoveryPrediction(
            id=f"pred_{uuid.uuid4().hex[:12]}",
            opportunity_id=opportunity.id,
            action_type=action,
            probability=prob,
            expected_gross_recovery_paise=expected_gross,
            expected_net_recovery_paise=expected_net,
            action_cost_paise=action_cost,
            incentive_cost_paise=incentive_cost,
            fatigue_penalty_paise=fatigue_penalty,
            model_version=model_version,
        )
        db.add(prediction)
        predictions.append(prediction)

    # Calculate overall recovery probability as the max of all action probabilities
    if predictions:
        opportunity.recovery_probability = max(p.probability for p in predictions)
    else:
        opportunity.recovery_probability = 0.0

    return predictions
