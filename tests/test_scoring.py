"""
RecoverOS — Opportunity Scoring and Prediction Tests
"""

import pytest
from datetime import datetime, timezone

from apps.api.models.tables import (
    RevenueEvent,
    RecoveryPrediction,
    EventType,
    PaymentMethod,
    ActionType,
)
from domain.actions.config import is_action_eligible, get_eligible_actions, ACTION_COSTS
from domain.opportunities.service import calculate_fatigue_risk, extract_risk_flags, create_opportunity_from_event
from domain.opportunities.scoring import score_opportunity_actions
from ml.models.probability_model import RecoveryProbabilityModel


# Mock class for database session to avoid active DB requirements in unit tests
class MockSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def rollback(self):
        pass


@pytest.fixture
def mock_event():
    return RevenueEvent(
        id="evt_test123",
        merchant_id="merchant_1",
        customer_id="customer_1",
        event_type=EventType.PAYMENT_FAILURE,
        amount_paise=100000,  # ₹1,000
        currency="INR",
        timestamp=datetime.now(timezone.utc),
        payment_method=PaymentMethod.UPI,
        failure_reason="UPI_TIMEOUT",
        attempt_count=1,
        previous_success=True,
        previous_recovery_success=False,
        previous_contact_count=1,
        last_contact_hours_ago=12.0,
        customer_tenure_days=100,
        days_since_last_purchase=10,
        customer_intent_score=0.75,
        eligible_for_recovery=True,
    )


# ─── Fatigue Risk Tests ────────────────────────────────────────────────────


class TestFatigueRisk:
    def test_zero_contacts_has_zero_fatigue(self):
        assert calculate_fatigue_risk(0, None) == 0.0
        assert calculate_fatigue_risk(0, 1.0) == 0.0

    def test_higher_contacts_increase_fatigue(self):
        low_fatigue = calculate_fatigue_risk(1, 24.0)
        high_fatigue = calculate_fatigue_risk(3, 24.0)
        assert high_fatigue > low_fatigue

    def test_recency_increases_fatigue(self):
        recent = calculate_fatigue_risk(2, 2.0)
        distant = calculate_fatigue_risk(2, 73.0)
        assert recent > distant

    def test_fatigue_is_clamped(self):
        assert calculate_fatigue_risk(10, 0.5) == 1.0


# ─── Action Eligibility Tests ──────────────────────────────────────────────


class TestActionEligibility:
    def test_opt_out_makes_all_ineligible(self, mock_event):
        mock_event.eligible_for_recovery = False
        for action in ActionType:
            assert not is_action_eligible(action, mock_event)

    def test_payment_failure_eligibility(self, mock_event):
        eligible = get_eligible_actions(mock_event)
        assert ActionType.RETRY_PAYMENT in eligible
        assert ActionType.ALTERNATE_PAYMENT_METHOD in eligible
        assert ActionType.SEND_RECOVERY_LINK in eligible

    def test_checkout_abandonment_eligibility(self, mock_event):
        mock_event.event_type = EventType.CHECKOUT_ABANDONMENT
        mock_event.payment_method = PaymentMethod.CREDIT_CARD
        eligible = get_eligible_actions(mock_event)
        assert ActionType.RETRY_PAYMENT not in eligible
        assert ActionType.SEND_REMINDER in eligible

    def test_retry_payment_attempt_limit(self, mock_event):
        mock_event.attempt_count = 3
        assert not is_action_eligible(ActionType.RETRY_PAYMENT, mock_event)


# ─── Risk Flags Tests ──────────────────────────────────────────────────────


class TestRiskFlags:
    def test_high_value_flag(self, mock_event):
        mock_event.amount_paise = 6_000_000  # ₹60,000
        flags = extract_risk_flags(mock_event)
        assert "HIGH_VALUE" in flags
        assert "LOW_VALUE" not in flags

    def test_low_value_flag(self, mock_event):
        mock_event.amount_paise = 500  # ₹5
        flags = extract_risk_flags(mock_event)
        assert "LOW_VALUE" in flags
        assert "HIGH_VALUE" not in flags

    def test_fatigue_flag(self, mock_event):
        mock_event.previous_contact_count = 3
        flags = extract_risk_flags(mock_event)
        assert "HIGH_FATIGUE" in flags


# ─── Expected Recovery Calculations Tests ──────────────────────────────────


class TestScoringCalculations:
    def test_expected_net_recovery_calculations(self, mock_event):
        db = MockSession()
        opp = create_opportunity_from_event(db, mock_event)
        model = RecoveryProbabilityModel()

        # Run scoring
        score_opportunity_actions(db, opp, mock_event, model)

        assert len(db.added) > 1  # 1 opportunity + several predictions
        
        predictions = [obj for obj in db.added if isinstance(obj, RecoveryPrediction)]
        assert len(predictions) > 0

        for pred in predictions:
            # Expected Gross = Amount * Prob
            expected_gross = int(opp.amount_at_risk_paise * pred.probability)
            assert pred.expected_gross_recovery_paise == expected_gross

            # Cost lookup check
            expected_cost = ACTION_COSTS[pred.action_type]
            assert pred.action_cost_paise == expected_cost

            # Expected Net = Gross - Cost - Incentive - Fatigue
            expected_net = (
                pred.expected_gross_recovery_paise
                - pred.action_cost_paise
                - pred.incentive_cost_paise
                - pred.fatigue_penalty_paise
            )
            assert pred.expected_net_recovery_paise == expected_net
            assert isinstance(pred.expected_net_recovery_paise, int)
