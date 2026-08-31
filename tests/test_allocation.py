"""
RecoverOS — Allocation Solver Tests
"""

import pytest
from datetime import datetime, timezone

from apps.api.models.tables import (
    RevenueEvent, RecoveryOpportunity, RecoveryPrediction, RecoveryDecision,
    EventType, PaymentMethod, ActionType, DecisionType, BusinessPolicy,
)
from optimization.allocator import GreedyAllocator
from optimization.constraints import AllocationConstraints


class MockDB:
    def __init__(self):
        self.opportunities = []
        self.predictions = []
        self.decisions = []
        self.policies = []
        self.committed = False

    def query(self, model):
        # Extremely simplified mock query to support allocator queries
        class QuerySet:
            def __init__(self, items, mock_db):
                self.items = items
                self.mock_db = mock_db

            def join(self, *args, **kwargs):
                return self

            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return self.items

            def count(self):
                return len(self.items)

            def order_by(self, *args):
                return self

        if model == RecoveryOpportunity:
            return QuerySet(self.opportunities, self)
        elif model == RecoveryPrediction:
            return QuerySet(self.predictions, self)
        elif model == RecoveryDecision:
            return QuerySet(self.decisions, self)
        return QuerySet([], self)

    def add(self, obj):
        if isinstance(obj, RecoveryDecision):
            self.decisions.append(obj)

    def commit(self):
        self.committed = True

    def flush(self):
        pass


@pytest.fixture
def mock_db():
    db = MockDB()
    # Mock some opportunities & predictions
    evt1 = RevenueEvent(
        id="evt_1",
        merchant_id="merchant_test",
        customer_id="cust_1",
        event_type=EventType.PAYMENT_FAILURE,
        amount_paise=100000,
        payment_method=PaymentMethod.UPI,
        failure_reason="UPI_TIMEOUT",
        eligible_for_recovery=True,
    )
    opp1 = RecoveryOpportunity(
        id="opp_1",
        event_id="evt_1",
        amount_at_risk_paise=100000,
        revenue_event=evt1,
        eligible_actions=[ActionType.ALTERNATE_PAYMENT_METHOD.value, ActionType.SEND_RECOVERY_LINK.value],
    )
    pred1a = RecoveryPrediction(
        opportunity_id="opp_1",
        action_type=ActionType.ALTERNATE_PAYMENT_METHOD,
        probability=0.85,
        expected_net_recovery_paise=80000,
    )
    pred1b = RecoveryPrediction(
        opportunity_id="opp_1",
        action_type=ActionType.SEND_RECOVERY_LINK,
        probability=0.60,
        expected_net_recovery_paise=50000,
    )

    db.opportunities.append(opp1)
    db.predictions.extend([pred1a, pred1b])

    # Unprofitable opportunity
    evt2 = RevenueEvent(
        id="evt_2",
        merchant_id="merchant_test",
        customer_id="cust_2",
        event_type=EventType.PAYMENT_FAILURE,
        amount_paise=100,  # ₹1
        eligible_for_recovery=True,
    )
    opp2 = RecoveryOpportunity(
        id="opp_2",
        event_id="evt_2",
        amount_at_risk_paise=100,
        revenue_event=evt2,
        eligible_actions=[ActionType.SEND_RECOVERY_LINK.value],
    )
    pred2 = RecoveryPrediction(
        opportunity_id="opp_2",
        action_type=ActionType.SEND_RECOVERY_LINK,
        probability=0.20,
        expected_net_recovery_paise=-900,  # Negative Net Recovery
    )
    db.opportunities.append(opp2)
    db.predictions.append(pred2)

    return db


class TestAllocationSolver:
    def test_greedy_allocation_net_recovery_prioritization(self, mock_db):
        allocator = GreedyAllocator(mock_db, "merchant_test")
        
        # Override policies to simplify tests
        allocator.constraints.max_automated_actions = 10
        allocator.constraints.min_probability = 0.50

        result = allocator.allocate_portfolio()

        assert result["total_processed"] == 2
        assert result["allocated_act"] == 1  # Only opp_1 is profitable
        assert result["allocated_suppress"] == 1  # opp_2 suppressed (negative net)

        # Check decision details
        decision = mock_db.decisions[0]
        assert decision.opportunity_id == "opp_1"
        assert decision.decision == DecisionType.ACT
        assert decision.recommended_action == ActionType.ALTERNATE_PAYMENT_METHOD

        suppressed_decision = mock_db.decisions[1]
        assert suppressed_decision.opportunity_id == "opp_2"
        assert suppressed_decision.decision == DecisionType.SUPPRESS
        assert suppressed_decision.recommended_action is None

    def test_allocation_capacity_exhaustion(self, mock_db):
        allocator = GreedyAllocator(mock_db, "merchant_test")
        
        # Set max actions to 0 to simulate capacity exhaustion
        allocator.constraints.max_automated_actions = 0

        result = allocator.allocate_portfolio()

        assert result["allocated_act"] == 0
        # The profitable opportunity (opp_1) gets suppressed because capacity is 0
        assert result["allocated_suppress"] == 2
