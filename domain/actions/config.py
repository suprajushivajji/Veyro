"""
RecoverOS — Candidate Actions Configuration

Defines configuration (costs, fatigue penalties, defaults) and eligibility
rules for all recovery actions.
All currency inputs/outputs are in integer paise (minor units).
"""

from typing import Dict, Any, List
from apps.api.models.tables import ActionType, EventType, PaymentMethod, RevenueEvent


# Operational costs of executing each action (in paise)
ACTION_COSTS: Dict[ActionType, int] = {
    ActionType.RETRY_PAYMENT: 200,                # ₹2
    ActionType.ALTERNATE_PAYMENT_METHOD: 500,     # ₹5
    ActionType.SEND_RECOVERY_LINK: 1000,          # ₹10
    ActionType.SEND_REMINDER: 100,                # ₹1
    ActionType.HUMAN_REVIEW: 15000,               # ₹150
}

# Base effectiveness of actions (used in baseline heuristics)
# Represents probability of success under perfect conditions
ACTION_BASE_EFFECTIVENESS: Dict[ActionType, float] = {
    ActionType.RETRY_PAYMENT: 0.60,
    ActionType.ALTERNATE_PAYMENT_METHOD: 0.70,
    ActionType.SEND_RECOVERY_LINK: 0.50,
    ActionType.SEND_REMINDER: 0.35,
    ActionType.HUMAN_REVIEW: 0.80,
}

# Fatigue impact per action (multiplier for penalty calculation)
ACTION_FATIGUE_IMPACT: Dict[ActionType, float] = {
    ActionType.RETRY_PAYMENT: 0.1,    # Low direct fatigue (system retries)
    ActionType.ALTERNATE_PAYMENT_METHOD: 0.3, # Medium direct fatigue
    ActionType.SEND_RECOVERY_LINK: 0.8,       # High fatigue (sms/email ping)
    ActionType.SEND_REMINDER: 0.5,            # Medium-high fatigue
    ActionType.HUMAN_REVIEW: 0.2,             # Low fatigue (often high-touch / phone review)
}


def is_action_eligible(action_type: ActionType, event: RevenueEvent) -> bool:
    """
    Check if a recovery action is eligible for a given revenue event.
    Returns True if eligible, False otherwise.
    """
    # Enforce basic opt-out rule first. Missing eligibility should not silently
    # block a valid action in test/mock usage or partially populated records.
    if event.eligible_for_recovery is False:
        return False

    # Check eligibility based on event type & method constraints
    if action_type == ActionType.RETRY_PAYMENT:
        # Retries are only relevant for payment/subscription/mandate failures
        if event.event_type not in (EventType.PAYMENT_FAILURE, EventType.SUBSCRIPTION_FAILURE, EventType.MANDATE_FAILURE):
            return False
        # Do not automatically retry if attempts are already high
        if event.attempt_count >= 3:
            return False
        # Only retry if payment method was direct/automated (Card, Netbanking, UPI, Mandates)
        if event.payment_method not in (PaymentMethod.CREDIT_CARD, PaymentMethod.DEBIT_CARD, PaymentMethod.NETBANKING, PaymentMethod.UPI, PaymentMethod.NACH):
            return False
        return True

    elif action_type == ActionType.ALTERNATE_PAYMENT_METHOD:
        # Alternate payment methods need another action option
        if event.event_type not in (EventType.PAYMENT_FAILURE, EventType.SUBSCRIPTION_FAILURE):
            return False
        # If user has only failed once, or UPI failed and they previously completed cards (or vice-versa)
        return True

    elif action_type == ActionType.SEND_RECOVERY_LINK:
        # Recovery links work for payment, subscription, overdue receivables
        # Not applicable if they have high contact fatigue
        if event.previous_contact_count >= 4:
            return False
        return True

    elif action_type == ActionType.SEND_REMINDER:
        # Reminders are primarily for checkout abandonments and overdue receivables, or SaaS subs
        if event.event_type not in (EventType.CHECKOUT_ABANDONMENT, EventType.OVERDUE_RECEIVABLE, EventType.SUBSCRIPTION_FAILURE):
            return False
        if event.previous_contact_count >= 3:
            return False
        return True

    elif action_type == ActionType.HUMAN_REVIEW:
        # Human reviews are expensive but always theoretically eligible.
        # Guardrails will suppress if low value, but policy-wise it's eligible.
        return True

    return False


def get_eligible_actions(event: RevenueEvent) -> List[ActionType]:
    """Get all eligible actions for a revenue event."""
    return [action for action in ActionType if is_action_eligible(action, event)]
