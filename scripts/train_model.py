"""
RecoverOS — Model Training Script

Simulates historical recovery outcomes based on the synthetic data
distribution, trains a Random Forest classifier, evaluates it using
proper ML metrics (ROC-AUC, Precision, Recall), and serializes it.
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score, brier_score_loss

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from apps.api.database import get_db_session
from apps.api.models.tables import RevenueEvent, ActionType, PaymentMethod, EventType
from ml.models.probability_model import RecoveryProbabilityModel, MODEL_PATH

SEED = 42
rng = np.random.default_rng(SEED)


def load_events_from_db():
    """Load revenue events from local database if seeded, otherwise load from json."""
    dataset_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "dataset")
    events_path = os.path.join(dataset_dir, "revenue_events.json")
    
    if os.path.exists(events_path):
        print(f"Loading events from JSON file: {events_path}")
        with open(events_path, "r") as f:
            raw_data = json.load(f)
        
        # Simple class mock for extracting features
        class MockEvent:
            def __init__(self, d):
                self.id = d["id"]
                self.amount_paise = d["amount_paise"]
                self.event_type = EventType(d["event_type"])
                self.payment_method = PaymentMethod(d["payment_method"]) if d.get("payment_method") else None
                self.failure_reason = d.get("failure_reason")
                self.attempt_count = d.get("attempt_count", 0)
                self.previous_success = d.get("previous_success", False)
                self.previous_recovery_success = d.get("previous_recovery_success", False)
                self.previous_contact_count = d.get("previous_contact_count", 0)
                self.last_contact_hours_ago = d.get("last_contact_hours_ago")
                self.customer_tenure_days = d.get("customer_tenure_days", 0)
                self.days_since_last_purchase = d.get("days_since_last_purchase")
                self.customer_intent_score = d.get("customer_intent_score", 0.5)
                self.invoice_age_days = d.get("invoice_age_days")
                self.pattern_flags = d.get("pattern_flags")
                self.eligible_for_recovery = d.get("eligible_for_recovery", True)
        
        return [MockEvent(e) for e in raw_data]
    else:
        print("Dataset not found. Generating simulated records in-memory...")
        # Fallback to loading from db session if available
        try:
            with get_db_session() as session:
                events = session.query(RevenueEvent).all()
                if events:
                    print(f"Loaded {len(events)} events from database.")
                    return events
        except Exception as e:
            print(f"Could not connect to database: {e}")
        
        print("Error: No data available. Run scripts/generate_data.py first.")
        sys.exit(1)


def generate_training_data(events):
    """
    Generate synthetic action-outcome training labels.
    For each event, we evaluate possible actions and simulate outcomes
    using the heuristic rules with some added random noise.
    """
    print("Generating action-outcome simulation records for training...")
    heuristic_model = RecoveryProbabilityModel()
    
    rows = []
    labels = []
    
    for event in events:
        # Evaluate all actions
        for action in ActionType:
            # Skip if totally ineligible to keep dataset clean
            # (but keep some ineligible to let ML learn rules)
            prob = heuristic_model._predict_heuristic(event, action)
            
            # Simulate true outcome based on the calculated probability + noise
            outcome = 1 if rng.random() < prob else 0
            
            features = RecoveryProbabilityModel.extract_features(event, action)
            rows.append(features)
            labels.append(outcome)
            
    df = pd.DataFrame(rows)
    y = np.array(labels)
    return df, y


def train():
    events = load_events_from_db()
    X, y = generate_training_data(events)
    
    print(f"Dataset compiled. Shape: {X.shape}, Target Positive Rate: {y.mean():.1%}")
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)
    
    print("Training Random Forest Classifier...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=SEED,
        n_jobs=-1
    )
    model.fit(X_train, y_train)
    
    # Evaluate
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]
    
    print("\n" + "="*50)
    print("           ML Model Evaluation Metrics")
    print("="*50)
    
    print("\nClassification Report:")
    print(classification_report(y_test, preds))
    
    auc = roc_auc_score(y_test, probs)
    print(f"ROC-AUC Score:      {auc:.4f}")
    
    brier = brier_score_loss(y_test, probs)
    print(f"Brier Score Loss:   {brier:.4f} (lower is better, checks calibration)")
    
    # Feature importance
    importances = model.feature_importances_
    feat_imp = pd.Series(importances, index=X.columns).sort_values(ascending=False)
    
    print("\nTop 10 Feature Importances:")
    for name, imp in feat_imp.head(10).items():
        print(f"  {name:30s}: {imp:.4f}")
    
    # Save the model
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    payload = {
        "model": model,
        "feature_names": list(X.columns),
        "metrics": {
            "roc_auc": float(auc),
            "brier_score": float(brier),
            "positive_rate": float(y.mean())
        }
    }
    joblib.dump(payload, MODEL_PATH)
    print(f"\nModel saved successfully to {MODEL_PATH}")
    print("="*50 + "\n")


if __name__ == "__main__":
    train()
