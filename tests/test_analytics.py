"""
RecoverOS — Analytics, Simulation, and Audit Trail Tests
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from apps.api.models.tables import (
    RevenueEvent, RecoveryOpportunity, RecoveryPrediction,
    EventType, PaymentMethod, ActionType, AuditEvent,
)
from apps.api.routes.war_room import get_war_room_analysis
from apps.api.routes.simulator import run_intervention_simulation, SimulationRequest


class MockWarRoomDB:
    def __init__(self, events):
        self.events = events

    def query(self, model):
        class MockQuery:
            def __init__(self, items):
                self.items = items
            def filter(self, *args, **kwargs):
                return self
            def scalar(self):
                return len(self.items)
            def first(self):
                # Mock average/sum tuple response
                if not self.items:
                    return (0, 0)
                tot_amt = sum(e.amount_paise for e in self.items)
                return (len(self.items), tot_amt)
        return MockQuery(self.events)

    def execute(self, *args, **kwargs):
        # Support raw SQL check
        class MockResult:
            def scalar(self):
                return len(self.events)
        return MockResult()


@pytest.fixture
def mock_degradation_events():
    events = []
    # Create UPI timeouts concentrated around 11:00 PM IST (17:30 UTC)
    for i in range(10):
        evt = RevenueEvent(
            id=f"evt_sys_{i}",
            merchant_id="merchant_test",
            customer_id=f"cust_{i}",
            event_type=EventType.PAYMENT_FAILURE,
            amount_paise=100000,
            payment_method=PaymentMethod.UPI,
            failure_reason="UPI_TIMEOUT",
            timestamp=datetime(2025, 8, 25, 17, 30, 0, tzinfo=timezone.utc),
        )
        events.append(evt)
    return events


class TestAnalyticsRoutes:
    def test_war_room_detects_systemic_upi_leak(self, mock_degradation_events):
        db = MockWarRoomDB(mock_degradation_events)
        
        # Call route function directly
        result = get_war_room_analysis("merchant_test", db)

        assert result["upi_failures_count"] == 10
        assert len(result["systemic_leaks_detected"]) == 1
        
        anomaly = result["systemic_leaks_detected"][0]
        assert "UPI Timeout" in anomaly["title"]
        assert anomaly["confidence"] == 0.94
        assert "temporal concentration" in anomaly["root_cause_explanation"].lower()


class MockSimulatorDB:
    def __init__(self, opportunities, predictions):
        self.opportunities = opportunities
        self.predictions = predictions
        self.committed = False

    def query(self, model):
        class MockQuery:
            def __init__(self, items):
                self.items = items
            def join(self, *args, **kwargs):
                return self
            def filter(self, *args, **kwargs):
                return self
            def all(self):
                return self.items
        if model == RecoveryOpportunity:
            return MockQuery(self.opportunities)
        elif model == RecoveryPrediction:
            return MockQuery(self.predictions)
        return MockQuery([])

    def commit(self):
        self.committed = True


class TestSimulationRoutes:
    def test_simulator_does_not_commit_changes(self):
        evt = RevenueEvent(
            id="evt_sim",
            merchant_id="merchant_test",
            customer_id="cust_sim",
            event_type=EventType.PAYMENT_FAILURE,
            amount_paise=100000,
            eligible_for_recovery=True,
        )
        opp = RecoveryOpportunity(
            id="opp_sim",
            event_id="evt_sim",
            amount_at_risk_paise=100000,
            revenue_event=evt,
            eligible_actions=[ActionType.SEND_RECOVERY_LINK.value],
        )
        pred = RecoveryPrediction(
            opportunity_id="opp_sim",
            action_type=ActionType.SEND_RECOVERY_LINK,
            probability=0.75,
            expected_net_recovery_paise=70000,
        )

        db = MockSimulatorDB([opp], [pred])
        req = SimulationRequest(
            merchant_id="merchant_test",
            max_capacity=10,
            min_probability=0.50,
            discount_budget_inr=1000.0,
        )

        result = run_intervention_simulation(req, db)

        # Confirm simulation returned correct expected gross/net estimates
        assert result["total_opportunities"] == 1
        assert result["selected_opportunities"] == 1
        assert result["expected_net_recovery_inr"] == 700.0
        
        # Verify that NO changes were committed to database (dry-run check)
        assert db.committed is False
