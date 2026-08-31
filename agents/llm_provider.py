"""
RecoverOS — LLM Provider Abstraction Layer

Provides a clean interface for querying LLM models (Gemini, OpenAI).
Includes a robust rule-based mock engine fallback for local/offline runs.
"""

import os
import json
from typing import Dict, Any, Optional

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class LLMProvider:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "mock").lower()
        self.api_key = os.getenv("LLM_API_KEY")
        self.model_name = os.getenv("LLM_MODEL")

        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Configure credentials for selected API providers."""
        if self.provider == "gemini" and self.api_key:
            if GEMINI_AVAILABLE:
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model_name or "gemini-2.0-flash")
            else:
                print("Warning: google-generativeai library not installed. Falling back to Mock.")
                self.provider = "mock"

        elif self.provider == "openai" and self.api_key:
            if OPENAI_AVAILABLE:
                self.client = OpenAI(api_key=self.api_key)
            else:
                print("Warning: openai library not installed. Falling back to Mock.")
                self.provider = "mock"
        else:
            self.provider = "mock"

    def query_json(self, prompt: str, schema_description: str) -> Dict[str, Any]:
        """
        Query the LLM expecting a structured JSON response.
        Falls back to rule-based mock engine if offline.
        """
        if self.provider == "mock" or not self.client:
            return self._query_mock(prompt)

        try:
            if self.provider == "gemini":
                # Request JSON structured output from Gemini
                response = self.client.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                return json.loads(response.text)

            elif self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model_name or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"You are a helpful assistant. You must output structured JSON matching: {schema_description}"},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"Warning: LLM API error: {e}. Falling back to mock engine.")
            return self._query_mock(prompt)

    def _query_mock(self, prompt: str) -> Dict[str, Any]:
        """
        A deterministic mock engine that extracts keywords from the prompt context
        to generate realistic LLM-style decision explanations.
        """
        # Lowercase prompt for keyword scanning
        lp = prompt.lower()
        
        decision = "ACT"
        action = "SEND_RECOVERY_LINK"
        evidence = []
        reason = "Target customer has active tenure and positive transaction history."

        # Extract context attributes from prompt via simple rules
        if "timeout" in lp or "upi_timeout" in lp:
            action = "ALTERNATE_PAYMENT_METHOD"
            reason = "The customer previously completed payments via UPI, the current UPI transaction timed out, and there has been no prior recovery contact. Route to alternate options."
            evidence = ["upi timeout detected", "previous success profile", "no recent contact"]
        elif "insufficient_funds" in lp or "funds" in lp:
            action = "SEND_REMINDER"
            reason = "Payment failed due to insufficient funds. A gentle reminder link allows the customer to top up and complete payment."
            evidence = ["insufficient funds error", "recent purchase intent"]
        elif "abandonment" in lp or "checkout" in lp:
            action = "SEND_RECOVERY_LINK"
            reason = "Checkout abandoned prior to payment completion. Direct email link suggested to recover intent."
            evidence = ["checkout abandoned", "high cart value"]
        elif "overdue" in lp or "invoice" in lp:
            action = "SEND_REMINDER"
            reason = "Invoice is overdue. Standard reminder follow-up is appropriate."
            evidence = ["unpaid invoice age", "billing cycle reminder"]
            if "invoice_age_days: 90" in lp or "overdue_90" in lp:
                action = "HUMAN_REVIEW"
                decision = "REVIEW"
                reason = "Invoice is over 90 days overdue. Highly risk prone, manual escalation needed."
                evidence = ["extreme overdue invoice age", "failed automated communications"]

        # High value checks
        if "amount_paise" in lp:
            # Check for high value amounts in the prompt text
            for word in lp.split():
                if word.isdigit() and int(word) > 5000000:
                    decision = "REVIEW"
                    action = "HUMAN_REVIEW"
                    reason = "High-value opportunity requires operational review before executing contact."
                    evidence = ["value exceeds auto-approval limits"]
                    break

        # High fatigue checks
        if "previous_contact_count" in lp:
            for word in lp.split():
                if word.isdigit() and int(word) >= 3:
                    decision = "SUPPRESS"
                    action = None
                    reason = "Multiple previous recovery actions failed. Suppressing to prevent customer spam."
                    evidence = ["excessive contacts", "low intent score"]
                    break

        return {
            "decision": decision,
            "action": action,
            "reason": reason,
            "confidence": 0.88,
            "evidence": evidence
        }
