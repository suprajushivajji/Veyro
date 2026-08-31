"""
RecoverOS — Action Execution and Fallback Tests
"""

import pytest
from datetime import datetime, timezone

from apps.api.models.tables import (
    RecoveryAction, ActionAttempt, ActionStatus, ActionType,
    RevenueEvent, RecoveryOpportunity, RecoveryPrediction,
    DecisionType, ControlGroup, ControlGroupType, Order,
    PaymentMethod, EventType,
)
from simulation.control_group import assign_control_group, is_treatment_group
from simulation.action_executor import ActionExecutor
from simulation.outcomes import handle_execution_outcome


class MockDBQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args, **kwargs):
        return self

    def scalar(self):
        return self.items[0] if self.items else 0

    def first(self):
        return self.items[0] if self.items else None

    def count(self):
        return len(self.items)

    def all(self):
        return self.items


class MockDBSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.control_groups = []
        self.attempts = []
        self.actions = []
        self.orders = []

    def query(self, model):
        if model == ControlGroup:
            return MockDBQuery(self.control_groups)
        elif model == ActionAttempt:
            return MockDBQuery(self.attempts)
        elif model == RecoveryAction:
            return MockDBQuery(self.actions)
        elif model == Order:
            return MockDBQuery(self.orders)
        return MockDBQuery([])

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, ControlGroup):
            self.control_groups.append(obj)
        elif isinstance(obj, ActionAttempt):
            self.attempts.append(obj)
        elif isinstance(obj, RecoveryAction):
            self.actions.append(obj)

    def commit(self):
        self.committed = True

    def flush(self):
        pass


@pytest.fixture
def mock_action():
    evt = RevenueEvent(
        id="evt_test_exec",
        amount_paise=250000,
        event_type=EventType.PAYMENT_FAILURE,
        payment_method=PaymentMethod.UPI,
        failure_reason="UPI_TIMEOUT",
        attempt_count=0,
        previous_contact_count=0,
    )
    opp = RecoveryOpportunity(
        id="opp_test_exec",
        amount_at_risk_paise=250000,
        revenue_event=evt,
        recovery_probability=0.80,
    )
    from apps.api.models.tables import RecoveryDecision
    dec = RecoveryDecision(
        id="dec_test_exec",
        opportunity=opp,
        decision=DecisionType.ACT,
        recommended_action=ActionType.RETRY_PAYMENT,
    )
    act = RecoveryAction(
        id="act_test_exec",
        decision=dec,
        action_type=ActionType.RETRY_PAYMENT,
        status=ActionStatus.PENDING,
        idempotency_key="key_123",
    )
    return act


class TestControlGroupSplits:
    def test_stable_deterministic_split(self):
        evt1 = RevenueEvent(id="event_stable_1")
        evt2 = RevenueEvent(id="event_stable_2")
        db = MockDBSession()

        cg1 = assign_control_group(db, evt1)
        cg2 = assign_control_group(db, evt1)

        # Same ID must yield identical group
        assert cg1.group_type == cg2.group_type

        # Verify treatment checking helper matches group assignment
        is_treat = is_treatment_group(db, evt1.id)
        assert is_treat == (cg1.group_type == ControlGroupType.TREATMENT)


class TestActionExecutor:
    def test_idempotency_check_blocks_duplicate(self, mock_action):
        db = MockDBSession()
        executor = ActionExecutor(db)

        # Record a previous successful attempt
        success_attempt = ActionAttempt(
            action_id=mock_action.id,
            status=ActionStatus.SUCCESS,
            attempt_number=1,
            action_type=mock_action.action_type
        )
        db.add(success_attempt)

        # Re-execution should return the existing attempt immediately
        attempt = executor.execute_action(mock_action)
        assert attempt.id == success_attempt.id
        assert attempt.status == ActionStatus.SUCCESS


class TestFailureFallbacks:
    def test_retry_creates_fallback_action(self, mock_action):
        db = MockDBSession()
        
        # Simulate timeout attempt
        attempt = ActionAttempt(
            action_id=mock_action.id,
            attempt_number=1,
            action_type=ActionType.RETRY_PAYMENT,
            status=ActionStatus.TIMEOUT,
            error_code="GATEWAY_TIMEOUT",
        )
        db.attempts.append(attempt)

        # Handle outcome
        fallback = handle_execution_outcome(db, mock_action, attempt)

        # Confirm fallback scheduled
        assert fallback is not None
        assert fallback.action_type == ActionType.ALTERNATE_PAYMENT_METHOD
        assert mock_action.status == ActionStatus.FALLBACK
        assert len(db.actions) > 0

    def test_retry_limits_stop_cascades(self, mock_action):
        db = MockDBSession()
        
        # Simulate attempt 3 (limit reached)
        attempt = ActionAttempt(
            action_id=mock_action.id,
            attempt_number=3,
            action_type=ActionType.RETRY_PAYMENT,
            status=ActionStatus.TIMEOUT,
            error_code="GATEWAY_TIMEOUT",
        )
        db.attempts.append(attempt)

        fallback = handle_execution_outcome(db, mock_action, attempt)

        # No fallback should be scheduled
        assert fallback is None
        assert mock_action.status == ActionStatus.FAILED
