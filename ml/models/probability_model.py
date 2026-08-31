"""
RecoverOS — Recovery Probability Model

Calculates P(recovery | event, action).
Includes:
  1. A robust heuristic baseline that uses domain rules and correlations.
  2. A machine learning model wrapper that loads a scikit-learn model if trained.
"""

import os
import joblib
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

from apps.api.models.tables import RevenueEvent, ActionType, EventType, PaymentMethod
from domain.actions.config import ACTION_BASE_EFFECTIVENESS

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "recovery_predictor.joblib"
)


class RecoveryProbabilityModel:
    def __init__(self, model_path: str = MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.feature_names = None
        self._load_model()

    def _load_model(self):
        """Try to load a pre-trained scikit-learn model."""
        if os.path.exists(self.model_path):
            try:
                payload = joblib.load(self.model_path)
                self.model = payload.get("model")
                self.feature_names = payload.get("feature_names")
                print(f"Loaded trained ML model from {self.model_path}")
            except Exception as e:
                print(f"Warning: Failed to load ML model: {e}. Falling back to heuristics.")

    def predict_probability(self, event: RevenueEvent, action: ActionType) -> float:
        """
        Predict probability of recovery for a given event and action.
        P(recovery | event, action)
        """
        # If ML model is loaded, use it
        if self.model is not None:
            try:
                features = self.extract_features(event, action)
                df = pd.DataFrame([features])
                # Ensure correct column order
                if self.feature_names:
                    df = df[self.feature_names]
                prob = float(self.model.predict_proba(df)[0][1])
                return max(0.01, min(0.99, prob))
            except Exception as e:
                # Fallback on inference failure
                pass

        # Fallback / Heuristic Model
        return self._predict_heuristic(event, action)

    def _predict_heuristic(self, event: RevenueEvent, action: ActionType) -> float:
        """
        Heuristic calculation of P(recovery | event, action).
        Reflects correlations built into the synthetic dataset.
        """
        # Start with base action effectiveness
        prob = ACTION_BASE_EFFECTIVENESS.get(action, 0.50)

        # ─── Intent Factor (Major weight) ───────────────────────────
        intent = event.customer_intent_score or 0.5
        # Scale prob by intent score (0.0 to 1.0)
        prob = prob * (0.3 + 0.7 * intent)

        # ─── Fatigue Factor ──────────────────────────────────────────
        # Reduce probability if they have been repeatedly contacted
        if event.previous_contact_count > 0:
            fatigue_penalty = min(0.6, event.previous_contact_count * 0.15)
            # Recency modifier
            if event.last_contact_hours_ago is not None and event.last_contact_hours_ago < 24.0:
                fatigue_penalty *= 1.25
            prob *= (1.0 - fatigue_penalty)

        # ─── Attempt Factor ──────────────────────────────────────────
        # More failed payment attempts = lower probability of standard retry success
        if action == ActionType.RETRY_PAYMENT and event.attempt_count > 0:
            prob *= max(0.2, 1.0 - (event.attempt_count * 0.25))

        # ─── Event-Type Customizations ────────────────────────────────
        if event.event_type == EventType.CHECKOUT_ABANDONMENT:
            # Abandonments respond well to recovery links and reminders, poorly to retries
            if action in (ActionType.SEND_RECOVERY_LINK, ActionType.SEND_REMINDER):
                prob *= 1.2
            elif action == ActionType.RETRY_PAYMENT:
                prob = 0.01  # Can't retry if they didn't even submit payment details

        elif event.event_type == EventType.OVERDUE_RECEIVABLE:
            # Overdue receivables respond to reminders and human review, not direct retries
            if action == ActionType.RETRY_PAYMENT:
                prob = 0.01
            elif action == ActionType.HUMAN_REVIEW:
                prob *= 1.1
            # Age penalty
            if event.invoice_age_days:
                age_factor = max(0.1, 1.0 - (event.invoice_age_days / 120.0))
                prob *= age_factor

        # ─── Specific Payment Method Suitabilities ───────────────────
        if event.event_type == EventType.PAYMENT_FAILURE:
            # UPI timeouts recover extremely well via alternate payment method or recovery link
            if event.failure_reason == "UPI_TIMEOUT":
                if action == ActionType.ALTERNATE_PAYMENT_METHOD:
                    prob *= 1.3
                elif action == ActionType.SEND_RECOVERY_LINK:
                    prob *= 1.15
                elif action == ActionType.RETRY_PAYMENT:
                    prob *= 0.5  # Re-attempting UPI immediately is likely to time out again

            # Card failures due to insufficient funds recover poorly unless reminded later
            if event.failure_reason in ("CARD_INSUFFICIENT_FUNDS", "UPI_INSUFFICIENT_FUNDS"):
                if action == ActionType.RETRY_PAYMENT:
                    prob *= 0.2
                elif action == ActionType.SEND_REMINDER:
                    # Give them time to add funds
                    prob *= 1.1

        # ─── Customer History Boosts ────────────────────────────────
        if event.previous_success:
            prob *= 1.15
        if event.previous_recovery_success:
            prob *= 1.25

        # ─── Systemic Degradation (Pattern F) ────────────────────────
        # If there's systemic degradation, retries will fail. Alternate payment option is best.
        if event.pattern_flags and event.pattern_flags.get("systemic_degradation"):
            if action == ActionType.RETRY_PAYMENT:
                prob *= 0.1
            elif action == ActionType.ALTERNATE_PAYMENT_METHOD:
                prob *= 1.2

        return max(0.01, min(0.99, prob))

    @staticmethod
    def extract_features(event: RevenueEvent, action: ActionType) -> Dict[str, Any]:
        """Extract flat features for machine learning models."""
        last_contact = event.last_contact_hours_ago if event.last_contact_hours_ago is not None else 168.0
        days_since = event.days_since_last_purchase if event.days_since_last_purchase is not None else 365.0
        inv_age = event.invoice_age_days if event.invoice_age_days is not None else 0

        # Build feature map
        features = {
            "amount_paise": float(event.amount_paise),
            "attempt_count": float(event.attempt_count),
            "previous_success": 1.0 if event.previous_success else 0.0,
            "previous_recovery_success": 1.0 if event.previous_recovery_success else 0.0,
            "previous_contact_count": float(event.previous_contact_count),
            "last_contact_hours_ago": float(last_contact),
            "customer_tenure_days": float(event.customer_tenure_days),
            "days_since_last_purchase": float(days_since),
            "customer_intent_score": float(event.customer_intent_score or 0.5),
            "invoice_age_days": float(inv_age),
            "is_upi": 1.0 if event.payment_method == PaymentMethod.UPI else 0.0,
            "is_card": 1.0 if event.payment_method in (PaymentMethod.CREDIT_CARD, PaymentMethod.DEBIT_CARD) else 0.0,
            "is_upi_timeout": 1.0 if event.failure_reason == "UPI_TIMEOUT" else 0.0,
        }

        # One-hot encode Event Type
        for et in EventType:
            features[f"event_type_{et.value}"] = 1.0 if event.event_type == et else 0.0

        # One-hot encode Action Type (target query)
        for act in ActionType:
            features[f"action_{act.value}"] = 1.0 if action == act else 0.0

        return features
