"""
RecoverOS — Guardrail Compliance Engine Tests
"""

import pytest
from sqlalchemy.orm import Session

from apps.api.models.tables import (
    RecoveryDecision, RecoveryOpportunity, RevenueEvent, Customer,
    DecisionType, ActionType, EventType, PaymentMethod,
)
from domain.guardrails.engine import GuardrailEngine


class MockQuery:
    def __init__(self, item):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item


class MockDBSession:
    def __init__(self, customer=None):
        self.customer = customer

    def query(self, model):
        if model == Customer:
            return MockQuery(self.customer)
        return MockQuery(None)


@pytest.fixture
def base_decision():
    evt = RevenueEvent(
        id="evt_123",
        merchant_id="merchant_1",
        customer_id="cust_123",
        event_type=EventType.PAYMENT_FAILURE,
        amount_paise=10000,  # ₹100
        payment_method=PaymentMethod.UPI,
        failure_reason="UPI_TIMEOUT",
        attempt_count=0,
        previous_contact_count=0,
        eligible_for_recovery=True,
    )
    opp = RecoveryOpportunity(
        id="opp_123",
        event_id="evt_123",
        amount_at_risk_paise=10000,
        revenue_event=evt,
        fatigue_risk=0.1,
    )
    decision = RecoveryDecision(
        id="dec_123",
        opportunity_id="opp_123",
        opportunity=opp,
        decision=DecisionType.ACT,
        recommended_action=ActionType.SEND_RECOVERY_LINK,
        guardrail_passed=True,
    )
    return decision


class TestGuardrailEngine:
    def test_pass_standard_decision(self, base_decision):
        db = MockDBSession(customer=Customer(id="cust_123", opted_out=False))
        engine = GuardrailEngine(db, "merchant_1")
        
        checked = engine.evaluate_decision(base_decision)
        
        assert checked.decision == DecisionType.ACT
        assert checked.recommended_action == ActionType.SEND_RECOVERY_LINK
        assert checked.guardrail_passed is True

    def test_opt_out_override_to_suppress(self, base_decision):
        # Customer opted out
        db = MockDBSession(customer=Customer(id="cust_123", opted_out=True))
        engine = GuardrailEngine(db, "merchant_1")
        
        checked = engine.evaluate_decision(base_decision)
        
        assert checked.decision == DecisionType.SUPPRESS
        assert checked.recommended_action is None
        assert checked.guardrail_passed is False
        assert "opted out" in checked.guardrail_reason.lower()

    def test_contact_cap_override_to_suppress(self, base_decision):
        # 3 previous contacts (policy max is 2)
        base_decision.opportunity.revenue_event.previous_contact_count = 3
        db = MockDBSession(customer=Customer(id="cust_123", opted_out=False))
        engine = GuardrailEngine(db, "merchant_1")
        
        checked = engine.evaluate_decision(base_decision)
        
        assert checked.decision == DecisionType.SUPPRESS
        assert checked.recommended_action is None
        assert checked.guardrail_passed is False
        assert "contact count" in checked.guardrail_reason.lower()

    def test_high_value_override_to_review(self, base_decision):
        # ₹60,000 (limit is ₹50,000)
        base_decision.opportunity.amount_at_risk_paise = 6_000_000
        base_decision.opportunity.revenue_event.amount_paise = 6_000_000
        db = MockDBSession(customer=Customer(id="cust_123", opted_out=False))
        engine = GuardrailEngine(db, "merchant_1")
        
        checked = engine.evaluate_decision(base_decision)
        
        assert checked.decision == DecisionType.REVIEW
        assert checked.recommended_action == ActionType.HUMAN_REVIEW
        assert checked.guardrail_passed is False
        assert "exceeds auto-action limit" in checked.guardrail_reason.lower()

    def test_invalid_action_eligibility_override_to_review(self, base_decision):
        # RETRY_PAYMENT on CHECKOUT_ABANDONMENT is invalid
        base_decision.opportunity.revenue_event.event_type = EventType.CHECKOUT_ABANDONMENT
        base_decision.recommended_action = ActionType.RETRY_PAYMENT
        db = MockDBSession(customer=Customer(id="cust_123", opted_out=False))
        engine = GuardrailEngine(db, "merchant_1")
        
        checked = engine.evaluate_decision(base_decision)
        
        assert checked.decision == DecisionType.REVIEW
        assert checked.recommended_action == ActionType.HUMAN_REVIEW
        assert checked.guardrail_passed is False
        assert "ineligible" in checked.guardrail_reason.lower()
