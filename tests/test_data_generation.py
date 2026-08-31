"""
RecoverOS — Data Generation Validation Tests

Validates the synthetic dataset for:
  - Correct event count (≥ 10,000)
  - All 5 event types present
  - Required fields non-null
  - Amount values positive integers (paise)
  - Correlation checks
  - Pattern presence (A through G)
  - No duplicate event IDs
  - Foreign key integrity
  - Timestamp reasonableness
"""

import json
import os
import sys
from datetime import datetime

import pytest
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "dataset")


@pytest.fixture(scope="module")
def events():
    """Load generated events."""
    path = os.path.join(DATASET_DIR, "revenue_events.json")
    if not os.path.exists(path):
        pytest.skip("Dataset not generated yet. Run 'python scripts/generate_data.py' first.")
    with open(path, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def customers():
    """Load generated customers."""
    path = os.path.join(DATASET_DIR, "customers.json")
    if not os.path.exists(path):
        pytest.skip("Dataset not generated yet.")
    with open(path, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def merchants():
    """Load generated merchants."""
    path = os.path.join(DATASET_DIR, "merchants.json")
    if not os.path.exists(path):
        pytest.skip("Dataset not generated yet.")
    with open(path, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def orders():
    """Load generated orders."""
    path = os.path.join(DATASET_DIR, "orders.json")
    if not os.path.exists(path):
        pytest.skip("Dataset not generated yet.")
    with open(path, "r") as f:
        return json.load(f)


# ─── Basic Count Tests ─────────────────────────────────────────────────────


class TestEventCount:
    def test_minimum_event_count(self, events):
        """Must have at least 10,000 events."""
        assert len(events) >= 10_000, f"Expected ≥10,000 events, got {len(events)}"

    def test_customer_count(self, customers):
        """Must have ~2,000 customers."""
        assert len(customers) >= 1_800, f"Expected ~2,000 customers, got {len(customers)}"

    def test_merchant_count(self, merchants):
        """Must have 3 merchants."""
        assert len(merchants) == 3


# ─── Event Type Coverage ───────────────────────────────────────────────────


class TestEventTypes:
    REQUIRED_TYPES = {
        "PAYMENT_FAILURE",
        "CHECKOUT_ABANDONMENT",
        "SUBSCRIPTION_FAILURE",
        "MANDATE_FAILURE",
        "OVERDUE_RECEIVABLE",
    }

    def test_all_event_types_present(self, events):
        """All 5 event types must be present."""
        types = {e["event_type"] for e in events}
        missing = self.REQUIRED_TYPES - types
        assert not missing, f"Missing event types: {missing}"

    def test_event_type_distribution(self, events):
        """No single event type should dominate >60% or be <2%."""
        from collections import Counter
        counts = Counter(e["event_type"] for e in events)
        total = len(events)
        for et, count in counts.items():
            pct = count / total
            assert pct < 0.60, f"{et} is {pct:.1%} — too dominant"
            assert pct > 0.02, f"{et} is {pct:.1%} — too rare"


# ─── Required Fields ───────────────────────────────────────────────────────


class TestRequiredFields:
    REQUIRED_FIELDS = [
        "id", "merchant_id", "customer_id", "event_type",
        "amount_paise", "currency", "timestamp", "payment_method",
        "failure_reason", "attempt_count", "customer_intent_score",
        "eligible_for_recovery",
    ]

    def test_required_fields_present(self, events):
        """All required fields must be present in every event."""
        for i, event in enumerate(events[:100]):  # Check first 100
            for field in self.REQUIRED_FIELDS:
                assert field in event, f"Event {i} missing field: {field}"

    def test_no_null_required_fields(self, events):
        """Required fields must not be None."""
        critical_fields = ["id", "merchant_id", "customer_id", "event_type", "amount_paise", "timestamp"]
        for i, event in enumerate(events[:100]):
            for field in critical_fields:
                assert event[field] is not None, f"Event {i} has null {field}"


# ─── Amount Validation ─────────────────────────────────────────────────────


class TestAmounts:
    def test_amounts_are_positive(self, events):
        """All amounts must be positive."""
        for i, event in enumerate(events):
            assert event["amount_paise"] > 0, f"Event {i} has non-positive amount: {event['amount_paise']}"

    def test_amounts_are_integers(self, events):
        """Amounts must be integers (paise)."""
        for i, event in enumerate(events[:100]):
            assert isinstance(event["amount_paise"], int), f"Event {i} amount is not int: {type(event['amount_paise'])}"

    def test_currency_is_inr(self, events):
        """All events should have INR currency."""
        for event in events[:100]:
            assert event["currency"] == "INR"


# ─── No Duplicates ─────────────────────────────────────────────────────────


class TestUniqueness:
    def test_no_duplicate_event_ids(self, events):
        """Every event_id must be unique."""
        ids = [e["id"] for e in events]
        assert len(ids) == len(set(ids)), "Duplicate event IDs found"

    def test_no_duplicate_customer_ids(self, customers):
        """Every customer_id must be unique."""
        ids = [c["id"] for c in customers]
        assert len(ids) == len(set(ids)), "Duplicate customer IDs found"


# ─── Foreign Key Integrity ─────────────────────────────────────────────────


class TestForeignKeys:
    def test_event_customer_ids_valid(self, events, customers):
        """All customer_ids in events must reference valid customers."""
        customer_ids = {c["id"] for c in customers}
        for i, event in enumerate(events[:500]):
            assert event["customer_id"] in customer_ids, \
                f"Event {i} references invalid customer: {event['customer_id']}"

    def test_event_merchant_ids_valid(self, events, merchants):
        """All merchant_ids in events must reference valid merchants."""
        merchant_ids = {m["id"] for m in merchants}
        for event in events[:500]:
            assert event["merchant_id"] in merchant_ids

    def test_event_order_ids_exist(self, events, orders):
        """All order_ids in events should reference existing orders."""
        order_ids = {o["id"] for o in orders}
        for event in events[:500]:
            if event.get("order_id"):
                assert event["order_id"] in order_ids


# ─── Timestamp Validation ──────────────────────────────────────────────────


class TestTimestamps:
    def test_timestamps_are_valid(self, events):
        """All timestamps must be parseable ISO format."""
        for i, event in enumerate(events[:100]):
            try:
                datetime.fromisoformat(event["timestamp"])
            except ValueError:
                pytest.fail(f"Event {i} has invalid timestamp: {event['timestamp']}")

    def test_timestamps_in_reasonable_range(self, events):
        """Timestamps should be within the expected window."""
        for event in events[:100]:
            ts = datetime.fromisoformat(event["timestamp"])
            assert ts.year >= 2025, f"Timestamp too old: {ts}"
            assert ts.year <= 2026, f"Timestamp too far in future: {ts}"


# ─── Pattern Verification ──────────────────────────────────────────────────


class TestPatterns:
    def test_pattern_a_upi_timeouts(self, events):
        """Pattern A: Significant number of UPI timeouts."""
        upi_timeouts = sum(
            1 for e in events
            if e["payment_method"] == "UPI" and e["failure_reason"] == "UPI_TIMEOUT"
        )
        assert upi_timeouts >= 500, f"Pattern A: Only {upi_timeouts} UPI timeouts (expected ≥500)"

    def test_pattern_b_previous_upi_success(self, events):
        """Pattern B: Events from customers with previous UPI success."""
        prev_upi = sum(
            1 for e in events
            if e.get("pattern_flags") and e["pattern_flags"].get("previous_upi_success")
        )
        assert prev_upi >= 100, f"Pattern B: Only {prev_upi} prev UPI success events (expected ≥100)"

    def test_pattern_c_high_fatigue(self, events):
        """Pattern C: Customers with high contact counts."""
        fatigued = sum(1 for e in events if e["previous_contact_count"] >= 3)
        assert fatigued >= 200, f"Pattern C: Only {fatigued} fatigued events (expected ≥200)"

    def test_pattern_d_high_value(self, events):
        """Pattern D: High-value events requiring human approval."""
        high_val = sum(1 for e in events if e["amount_paise"] >= 5_000_000)
        assert high_val >= 100, f"Pattern D: Only {high_val} high-value events (expected ≥100)"

    def test_pattern_e_low_value(self, events):
        """Pattern E: Low-value events where intervention is uneconomical."""
        low_val = sum(1 for e in events if e["amount_paise"] < 10_000)
        assert low_val >= 200, f"Pattern E: Only {low_val} low-value events (expected ≥200)"

    def test_pattern_f_systemic_degradation(self, events):
        """Pattern F: Cluster of systemic payment degradation."""
        systemic = sum(
            1 for e in events
            if e.get("pattern_flags") and e["pattern_flags"].get("systemic_degradation")
        )
        assert systemic >= 100, f"Pattern F: Only {systemic} systemic events (expected ≥100)"

    def test_pattern_g_forced_fallback(self, events):
        """Pattern G: Events flagged for forced execution failure."""
        fallback = sum(
            1 for e in events
            if e.get("pattern_flags") and e["pattern_flags"].get("force_fallback")
        )
        assert fallback >= 50, f"Pattern G: Only {fallback} fallback events (expected ≥50)"


# ─── Correlation Checks ────────────────────────────────────────────────────


class TestCorrelations:
    def test_attempt_count_vs_intent(self, events):
        """Higher attempt count should correlate with lower intent score."""
        low_attempts = [e["customer_intent_score"] for e in events if e["attempt_count"] <= 1]
        high_attempts = [e["customer_intent_score"] for e in events if e["attempt_count"] >= 3]

        if low_attempts and high_attempts:
            mean_low = np.mean(low_attempts)
            mean_high = np.mean(high_attempts)
            assert mean_low > mean_high, \
                f"Intent should be lower with more attempts: low_att={mean_low:.3f}, high_att={mean_high:.3f}"

    def test_tenure_vs_intent(self, events):
        """Longer tenure should correlate with higher intent score."""
        new_customers = [e["customer_intent_score"] for e in events if e["customer_tenure_days"] < 90]
        old_customers = [e["customer_intent_score"] for e in events if e["customer_tenure_days"] > 365]

        if new_customers and old_customers:
            mean_new = np.mean(new_customers)
            mean_old = np.mean(old_customers)
            assert mean_old > mean_new, \
                f"Established customers should have higher intent: new={mean_new:.3f}, old={mean_old:.3f}"

    def test_contact_count_vs_intent(self, events):
        """Higher contact count should reduce intent (fatigue effect)."""
        no_contact = [e["customer_intent_score"] for e in events if e["previous_contact_count"] == 0]
        high_contact = [e["customer_intent_score"] for e in events if e["previous_contact_count"] >= 3]

        if no_contact and high_contact:
            mean_no = np.mean(no_contact)
            mean_high = np.mean(high_contact)
            assert mean_no > mean_high, \
                f"Fatigued customers should have lower intent: no={mean_no:.3f}, high={mean_high:.3f}"

    def test_event_types_have_different_intent(self, events):
        """Different event types should have meaningfully different intent distributions."""
        from collections import defaultdict
        intent_by_type = defaultdict(list)
        for e in events:
            intent_by_type[e["event_type"]].append(e["customer_intent_score"])

        means = {et: np.mean(scores) for et, scores in intent_by_type.items() if scores}
        # Subscription failures should generally have higher intent than overdue receivables
        if "SUBSCRIPTION_FAILURE" in means and "OVERDUE_RECEIVABLE" in means:
            assert means["SUBSCRIPTION_FAILURE"] > means["OVERDUE_RECEIVABLE"], \
                f"Sub failures should have higher intent than overdue: sub={means['SUBSCRIPTION_FAILURE']:.3f}, overdue={means['OVERDUE_RECEIVABLE']:.3f}"


# ─── Intent Score Range ────────────────────────────────────────────────────


class TestIntentScore:
    def test_intent_score_range(self, events):
        """Intent scores must be between 0 and 1."""
        for i, event in enumerate(events):
            score = event["customer_intent_score"]
            assert 0.0 <= score <= 1.0, f"Event {i} has invalid intent score: {score}"
