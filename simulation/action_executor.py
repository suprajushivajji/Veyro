"""
RecoverOS — Action Execution Simulator

Simulates connections to Razorpay Test Mode APIs.
Enforces idempotency keys, manages execution statuses, and introduces
correlated failures (timeouts, bank downs, success rates based on predictions).
"""

import uuid
import time
from typing import Dict, Any, Tuple
import numpy as np
from sqlalchemy.orm import Session

from apps.api.models.tables import (
    RecoveryAction, ActionAttempt, ActionStatus, ActionType,
    RevenueEvent, RecoveryOpportunity, RecoveryPrediction,
)

# Set up random generator
rng = np.random.default_rng(42)


class ActionExecutor:
    def __init__(self, db: Session):
        self.db = db

    def execute_action(self, action: RecoveryAction) -> ActionAttempt:
        """
        Executes a recovery action in simulation mode.
        Checks for idempotency constraints first.
        """
        # ─── 1. Idempotency Check ─────────────────────────────────
        # Ensure we do not execute the same action twice (prevent double charge/spam)
        existing_success = self.db.query(ActionAttempt).filter(
            ActionAttempt.action_id == action.id,
            ActionAttempt.status == ActionStatus.SUCCESS
        ).first()
        if existing_success:
            return existing_success

        # If there's an active execution running, return it (simple lock mock)
        active_attempt = self.db.query(ActionAttempt).filter(
            ActionAttempt.action_id == action.id,
            ActionAttempt.status == ActionStatus.EXECUTING
        ).first()
        if active_attempt:
            return active_attempt

        # Update action state to Executing
        action.status = ActionStatus.EXECUTING
        action.executed_at = time.strftime('%Y-%m-%d %H:%M:%S')
        self.db.flush()

        # Get parent details for context
        decision = action.decision
        opportunity = decision.opportunity
        event = opportunity.revenue_event

        # Retrieve prediction probability for this specific action type
        prediction = self.db.query(RecoveryPrediction).filter(
            RecoveryPrediction.opportunity_id == opportunity.id,
            RecoveryPrediction.action_type == action.action_type
        ).first()
        
        prob = prediction.probability if prediction else 0.50

        # Compile attempts count
        prev_attempts = self.db.query(ActionAttempt).filter(
            ActionAttempt.action_id == action.id
        ).count()
        attempt_number = prev_attempts + 1

        # ─── 2. Execution Simulation ──────────────────────────────
        # Start logging attempt
        attempt_id = f"att_{uuid.uuid4().hex[:12]}"
        
        # Emulate processing latency
        duration = int(rng.integers(150, 850))

        # Check Pattern constraints for demo scenarios:
        # Pattern G: Forced fallback cases must fail on their first attempt
        is_forced_fallback = False
        if event.pattern_flags and event.pattern_flags.get("force_fallback"):
            is_forced_fallback = True

        status = ActionStatus.SUCCESS
        error_code = None
        error_message = None

        if is_forced_fallback and attempt_number == 1:
            # Force first attempt to time out
            status = ActionStatus.TIMEOUT
            error_code = "GATEWAY_TIMEOUT"
            error_message = "Razorpay API Timeout: Bank servers failed to respond within 15 seconds."
        else:
            # Normal probabilistic execution
            # Success probability depends on prediction + minor noise
            roll = rng.random()
            if roll > prob:
                status = ActionStatus.FAILED
                error_code = "PAYMENT_DECLINED"
                error_message = "Transaction declined by card network: Insufficient funds or authentication error."

        # Save attempt log
        attempt = ActionAttempt(
            id=attempt_id,
            action_id=action.id,
            attempt_number=attempt_number,
            action_type=action.action_type,
            status=status,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration,
        )
        self.db.add(attempt)
        
        # Sync action status
        action.status = status
        action.completed_at = time.strftime('%Y-%m-%d %H:%M:%S')
        self.db.flush()

        return attempt
