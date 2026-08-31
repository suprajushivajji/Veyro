"""
RecoverOS — Outcomes and Fallbacks Engine

Processes the result of action executions.
Triggers success payouts or schedules automated fallback recovery loops.
"""

import uuid
from typing import Optional
from sqlalchemy.orm import Session

from apps.api.models.tables import (
    RecoveryAction, ActionAttempt, ActionStatus, ActionType,
    RecoveryOutcome, ControlGroup, Order, AuditEvent, DecisionType,
    RevenueEvent,
)
from domain.actions.config import is_action_eligible


def handle_execution_outcome(
    db: Session,
    action: RecoveryAction,
    attempt: ActionAttempt,
    max_retries: int = 3
) -> Optional[RecoveryAction]:
    """
    Evaluates action execution outcome.
    - On Success: Marks order as paid, logs recovery outcome, registers control group stats.
    - On Failure: Evaluates retry thresholds and schedules fallback actions if allowed.
    """
    decision = action.decision
    opportunity = decision.opportunity
    event = opportunity.revenue_event
    order = db.query(Order).filter(Order.id == event.order_id).first()

    # Create audit event log
    audit = AuditEvent(
        id=f"aud_{uuid.uuid4().hex[:12]}",
        event_id=event.id,
        customer_id=event.customer_id,
        decision_id=decision.id,
        action_id=action.id,
        decision=decision.decision,
        recommended_action=decision.recommended_action,
        executed_action=action.action_type,
        model_probability=opportunity.recovery_probability,
        expected_recovery_paise=opportunity.amount_at_risk_paise,
        expected_net_recovery_paise=0, # Computed earlier
        execution_status=attempt.status,
    )

    if attempt.status == ActionStatus.SUCCESS:
        # ─── SUCCESS PAYOUT ───────────────────────────────────────
        # Mark order paid
        if order:
            order.status = "paid"

        # Log recovery outcome
        outcome = RecoveryOutcome(
            id=f"out_{uuid.uuid4().hex[:12]}",
            event_id=event.id,
            action_id=action.id,
            recovered=True,
            recovered_amount_paise=opportunity.amount_at_risk_paise,
            recovery_method=action.action_type.value,
        )
        db.add(outcome)

        # Update control group stats for lift calculations
        cg = db.query(ControlGroup).filter(ControlGroup.event_id == event.id).first()
        if cg:
            cg.recovered = True
            cg.recovered_amount_paise = opportunity.amount_at_risk_paise

        # Finalize action status
        action.status = ActionStatus.SUCCESS
        
        # Complete audit log
        audit.recovered_amount_paise = opportunity.amount_at_risk_paise
        audit.guardrail_result = "SUCCESS"
        db.add(audit)
        db.commit()
        return None

    else:
        # ─── FAILURE & FALLBACK HANDLER ────────────────────────────
        audit.recovered_amount_paise = 0
        audit.guardrail_result = "FAILED"
        audit.guardrail_reason = f"Execution failed: {attempt.error_code} - {attempt.error_message}"

        # Evaluate if we can trigger a fallback action
        if attempt.attempt_number < max_retries:
            # Determine appropriate fallback action type
            fallback_type = _select_fallback_action(action.action_type, event)
            
            if fallback_type:
                # Schedule a fallback action with a unique idempotency key
                fallback_key = f"fallback_{action.id}_{attempt.attempt_number}"
                
                # Check if fallback action was already created to prevent loops
                existing_fallback = db.query(RecoveryAction).filter(
                    RecoveryAction.idempotency_key == fallback_key
                ).first()

                if not existing_fallback:
                    fallback_action = RecoveryAction(
                        id=f"act_{uuid.uuid4().hex[:12]}",
                        decision_id=decision.id,
                        idempotency_key=fallback_key,
                        action_type=fallback_type,
                        status=ActionStatus.PENDING,
                    )
                    db.add(fallback_action)
                    
                    # Update current attempt's link
                    attempt.fallback_action = fallback_type
                    action.status = ActionStatus.FALLBACK
                    
                    # Update audit record
                    audit.fallback_action = fallback_type
                    db.add(audit)
                    db.commit()
                    print(f"Fallback triggered: Scheduled {fallback_type.value} following {action.action_type.value} failure.")
                    return fallback_action

        # If retries exceeded or no valid fallback, log finalized failure
        outcome = RecoveryOutcome(
            id=f"out_{uuid.uuid4().hex[:12]}",
            event_id=event.id,
            action_id=action.id,
            recovered=False,
            recovered_amount_paise=0,
            recovery_method=action.action_type.value,
        )
        db.add(outcome)
        
        action.status = ActionStatus.FAILED
        db.add(audit)
        db.commit()
        return None


def _select_fallback_action(failed_type: ActionType, event: RevenueEvent) -> Optional[ActionType]:
    """
    Deterministic rule routing to decide on a fallback action.
    E.g. RETRY_PAYMENT fails → SEND_RECOVERY_LINK is safe fallback.
    """
    if failed_type == ActionType.RETRY_PAYMENT:
        # Card retry failed. Alternate PM or Recovery link is standard
        if is_action_eligible(ActionType.ALTERNATE_PAYMENT_METHOD, event):
            return ActionType.ALTERNATE_PAYMENT_METHOD
        elif is_action_eligible(ActionType.SEND_RECOVERY_LINK, event):
            return ActionType.SEND_RECOVERY_LINK

    elif failed_type == ActionType.ALTERNATE_PAYMENT_METHOD:
        # Alternate payment attempt failed. Link is safer fallback
        if is_action_eligible(ActionType.SEND_RECOVERY_LINK, event):
            return ActionType.SEND_RECOVERY_LINK

    elif failed_type == ActionType.SEND_RECOVERY_LINK:
        # Link failed (e.g. no click). Send final reminder follow-up
        if is_action_eligible(ActionType.SEND_REMINDER, event):
            return ActionType.SEND_REMINDER

    return None
