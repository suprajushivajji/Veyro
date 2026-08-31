"""
RecoverOS — AI Decision Agent

Formulates contexts, builds prompts, queries the LLM provider,
and parses structured recovery decisions.
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session

from apps.api.models.tables import RecoveryOpportunity, RevenueEvent, Customer
from agents.llm_provider import LLMProvider

SCHEMA_DESC = """
{
  "decision": "ACT" | "REVIEW" | "SUPPRESS",
  "action": "RETRY_PAYMENT" | "ALTERNATE_PAYMENT_METHOD" | "SEND_RECOVERY_LINK" | "SEND_REMINDER" | null,
  "reason": "text explaining the logic",
  "confidence": float (0.0 to 1.0),
  "evidence": ["list", "of", "findings"]
}
"""


class RecoveryDecisionAgent:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def analyze_opportunity(self, db: Session, opportunity: RecoveryOpportunity) -> Dict[str, Any]:
        """
        Synthesizes opportunity and customer history, builds LLM prompt,
        and requests structured decision reasoning.
        """
        event = opportunity.revenue_event
        customer = db.query(Customer).filter(Customer.id == event.customer_id).first()
        
        # Build customer stats profile
        cust_profile = ""
        if customer:
            cust_profile = f"""
            Customer Name: {customer.name}
            Tenure Days: {customer.customer_tenure_days}
            Total Transactions: {customer.total_transactions}
            Successful Transactions: {customer.successful_transactions}
            Lifetime Value (paise): {customer.lifetime_value_paise}
            Preferred Payment Method: {customer.preferred_payment_method.value if customer.preferred_payment_method else "None"}
            Days Since Last Purchase: {customer.days_since_last_purchase}
            Opted Out of Communications: {customer.opted_out}
            """

        # Formulate prompt
        prompt = f"""
        You are the RecoverOS Autonomous Decision Agent. Your goal is to review a revenue loss opportunity and recommend whether to ACT, REVIEW, or SUPPRESS the recovery intervention.

        ─── REVENUE RISK EVENT CONTEXT ───
        Event ID: {event.id}
        Event Type: {event.event_type.value}
        Amount at Risk (paise): {event.amount_paise}
        Payment Method: {event.payment_method.value if event.payment_method else "None"}
        Failure Reason: {event.failure_reason}
        Attempt Count (current txn): {event.attempt_count}
        Previous Success Rate: {event.previous_success}
        Previous Recovery Success: {event.previous_recovery_success}
        
        ─── CONTACT FREQUENCY & FATIGUE ───
        Previous Contact Count: {event.previous_contact_count}
        Hours Since Last Contact: {event.last_contact_hours_ago if event.last_contact_hours_ago is not None else "Never contacted"}
        Computed Fatigue Risk Score (0.0 to 1.0): {opportunity.fatigue_risk}
        
        ─── ELIGIBLE ACTIONS FOR THIS EVENT ───
        Allowed actions: {opportunity.eligible_actions}
        Risk Flags Detected: {opportunity.risk_flags}
        Customer Intent Score: {opportunity.customer_intent}

        ─── CUSTOMER HISTORY PROFILE ───
        {cust_profile}

        ─── DECISION RULES & MISSION GUIDELINES ───
        1. ACT: Choose if expected recovery probability is high, costs are low, and fatigue is negligible. Specifying which 'action' to execute is required.
        2. REVIEW: Choose if the transaction is extremely high value (>50,000 paise / ₹500) OR has high complexity that automated systems shouldn't run alone.
        3. SUPPRESS: Choose if the customer is fatigued (high contact count, recent contacts), opted-out, has negative net value, or has extremely low intent.

        Return structured JSON matching this schema:
        {SCHEMA_DESC}
        """

        # Query provider
        response = self.provider.query_json(prompt, SCHEMA_DESC)
        return response
