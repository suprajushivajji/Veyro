"""
RecoverOS — Revenue Opportunity Service

Handles mapping and translation from RevenueEvents to RecoveryOpportunities.
"""

import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from apps.api.models.tables import RevenueEvent, RecoveryOpportunity, ActionType
from domain.actions.config import get_eligible_actions


def calculate_fatigue_risk(previous_contact_count: int, last_contact_hours_ago: Optional[float]) -> float:
    """
    Calculate customer contact fatigue risk score between 0.0 and 1.0.
    Correlates positively with contact frequency and recency.
    """
    if previous_contact_count == 0:
        return 0.0

    # Base risk from contact count
    base_risk = min(0.8, previous_contact_count * 0.2)

    # Recency amplifier (if they were contacted recently, fatigue is higher)
    recency_amp = 1.0
    if last_contact_hours_ago is not None:
        if last_contact_hours_ago < 4.0:
            recency_amp = 1.25
        elif last_contact_hours_ago < 24.0:
            recency_amp = 1.10
        elif last_contact_hours_ago > 72.0:
            recency_amp = 0.50

    return min(1.0, base_risk * recency_amp)


def extract_risk_flags(event: RevenueEvent) -> List[str]:
    """Identify high-level risk flags based on event context."""
    flags = []

    # High contact fatigue
    if event.previous_contact_count >= 3:
        flags.append("HIGH_FATIGUE")

    # High payment attempts
    if event.attempt_count >= 3:
        flags.append("EXCESSIVE_ATTEMPTS")

    # Systemic degradation pattern
    if event.pattern_flags and event.pattern_flags.get("systemic_degradation"):
        flags.append("SYSTEMIC_DEGRADATION")

    # Extremely old receivables
    if event.invoice_age_days and event.invoice_age_days > 90:
        flags.append("INVOICE_CRITICAL_AGE")

    # High Value Opportunity
    if event.amount_paise >= 5_000_000:  # ₹50,000
        flags.append("HIGH_VALUE")

    # Low Value Opportunity
    if event.amount_paise < 10_000:  # ₹100
        flags.append("LOW_VALUE")

    return flags


def create_opportunity_from_event(db: Session, event: RevenueEvent) -> RecoveryOpportunity:
    """
    Maps a RevenueEvent into a RecoveryOpportunity.
    Does not save to DB immediately (requires commit by caller).
    """
    opp_id = f"opp_{uuid.uuid4().hex[:12]}"
    
    fatigue_risk = calculate_fatigue_risk(
        event.previous_contact_count,
        event.last_contact_hours_ago
    )

    eligible_actions = get_eligible_actions(event)
    risk_flags = extract_risk_flags(event)

    opportunity = RecoveryOpportunity(
        id=opp_id,
        event_id=event.id,
        amount_at_risk_paise=event.amount_paise,
        recovery_probability=0.0,  # Computed in next steps
        customer_intent=event.customer_intent_score or 0.5,
        fatigue_risk=fatigue_risk,
        eligible_actions=[action.value for action in eligible_actions],
        risk_flags=risk_flags,
    )

    db.add(opportunity)
    return opportunity
