"""
RecoverOS — Synthetic Data Generator

Generates 10,000+ realistic revenue-risk events with meaningful correlations.

Patterns (per PRD §31):
  A — Many UPI timeouts (concentrated 10PM-12AM)
  B — Customers with previous successful UPI payments (higher recovery intent)
  C — Customers with repeated recovery messages (high fatigue)
  D — High-value opportunities requiring human approval (>₹50,000)
  E — Low-value opportunities where intervention cost > expected recovery (<₹100)
  F — Systemic payment degradation cluster (same gateway, same time window)
  G — Events flagged for simulated execution failure (fallback scenarios)

Correlations:
  - attempt_count ↑ → recovery_probability ↓
  - customer_tenure_days ↑ + previous_success → recovery_probability ↑
  - previous_contact_count ↑ → fatigue_risk ↑
  - invoice_age_days ↑ → recovery_probability ↓
  - customer_intent_score correlated with recent activity and tenure
  - Different event types have different recoverability profiles
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import numpy as np
import pandas as pd

# Deterministic seed for reproducibility
SEED = 42
rng = np.random.default_rng(SEED)

# ─── Configuration ──────────────────────────────────────────────────────────

NUM_EVENTS = 10_500  # Generate slightly more than 10,000
NUM_CUSTOMERS = 2_000
NUM_MERCHANTS = 3

BASE_TIME = datetime(2025, 8, 25, 0, 0, 0, tzinfo=timezone.utc)
EVENT_WINDOW_DAYS = 7  # Events span 1 week

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "dataset")

# ─── Merchant Profiles ──────────────────────────────────────────────────────

MERCHANT_PROFILES = [
    {
        "id": "merchant_ecommerce_001",
        "name": "ShopKart India",
        "business_type": "ecommerce",
        "industry": "retail",
        "event_mix": {
            "PAYMENT_FAILURE": 0.45,
            "CHECKOUT_ABANDONMENT": 0.30,
            "SUBSCRIPTION_FAILURE": 0.05,
            "MANDATE_FAILURE": 0.05,
            "OVERDUE_RECEIVABLE": 0.15,
        },
        "amount_range_paise": (5000, 2500000),  # ₹50 - ₹25,000
        "customer_share": 0.50,
    },
    {
        "id": "merchant_saas_002",
        "name": "CloudSync Pro",
        "business_type": "saas",
        "industry": "technology",
        "event_mix": {
            "PAYMENT_FAILURE": 0.25,
            "CHECKOUT_ABANDONMENT": 0.10,
            "SUBSCRIPTION_FAILURE": 0.40,
            "MANDATE_FAILURE": 0.15,
            "OVERDUE_RECEIVABLE": 0.10,
        },
        "amount_range_paise": (49900, 9999900),  # ₹499 - ₹99,999
        "customer_share": 0.30,
    },
    {
        "id": "merchant_services_003",
        "name": "UrbanServe",
        "business_type": "services",
        "industry": "home_services",
        "event_mix": {
            "PAYMENT_FAILURE": 0.35,
            "CHECKOUT_ABANDONMENT": 0.20,
            "SUBSCRIPTION_FAILURE": 0.10,
            "MANDATE_FAILURE": 0.10,
            "OVERDUE_RECEIVABLE": 0.25,
        },
        "amount_range_paise": (20000, 1500000),  # ₹200 - ₹15,000
        "customer_share": 0.20,
    },
]

# ─── Failure Reasons by Event Type ──────────────────────────────────────────

FAILURE_REASONS = {
    "PAYMENT_FAILURE": {
        "UPI": ["UPI_TIMEOUT", "UPI_DECLINED", "UPI_PSP_ERROR", "UPI_INSUFFICIENT_FUNDS", "UPI_PIN_INCORRECT"],
        "CREDIT_CARD": ["CARD_DECLINED", "CARD_EXPIRED", "CARD_INSUFFICIENT_FUNDS", "CARD_CVV_MISMATCH", "CARD_3DS_FAILED"],
        "DEBIT_CARD": ["CARD_DECLINED", "CARD_EXPIRED", "CARD_INSUFFICIENT_FUNDS", "CARD_DAILY_LIMIT"],
        "NETBANKING": ["NB_TIMEOUT", "NB_SESSION_EXPIRED", "NB_BANK_DOWN", "NB_AUTHENTICATION_FAILED"],
        "WALLET": ["WALLET_INSUFFICIENT_BALANCE", "WALLET_EXPIRED", "WALLET_LIMIT_REACHED"],
        "EMI": ["EMI_NOT_ELIGIBLE", "EMI_BANK_DECLINED"],
        "NACH": ["MANDATE_EXPIRED", "MANDATE_INSUFFICIENT_FUNDS", "MANDATE_CANCELLED"],
    },
    "CHECKOUT_ABANDONMENT": ["CART_ABANDONED", "SESSION_TIMEOUT", "PRICE_COMPARISON", "SHIPPING_COST", "ACCOUNT_REQUIRED"],
    "SUBSCRIPTION_FAILURE": ["PAYMENT_FAILED", "CARD_EXPIRED", "INSUFFICIENT_FUNDS", "MANDATE_CANCELLED", "PLAN_DISCONTINUED"],
    "MANDATE_FAILURE": ["MANDATE_EXPIRED", "MANDATE_INSUFFICIENT_FUNDS", "MANDATE_CANCELLED", "MANDATE_LIMIT_EXCEEDED"],
    "OVERDUE_RECEIVABLE": ["INVOICE_OVERDUE_30", "INVOICE_OVERDUE_60", "INVOICE_OVERDUE_90", "INVOICE_DISPUTED", "INVOICE_PARTIAL_PAYMENT"],
}

SUBSCRIPTION_PLANS = ["basic_monthly", "pro_monthly", "enterprise_monthly", "basic_annual", "pro_annual"]

# ─── Helper Functions ───────────────────────────────────────────────────────


def gen_id(prefix: str = "") -> str:
    """Generate a UUID with optional prefix."""
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}" if prefix else uid


def gen_timestamp(base: datetime, offset_hours_range: tuple) -> datetime:
    """Generate a random timestamp within an offset range from base."""
    offset = rng.uniform(offset_hours_range[0], offset_hours_range[1])
    return base + timedelta(hours=offset)


def clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


# ─── Generate Merchants ────────────────────────────────────────────────────


def generate_merchants() -> list[dict]:
    """Generate merchant records."""
    merchants = []
    for profile in MERCHANT_PROFILES:
        merchants.append({
            "id": profile["id"],
            "name": profile["name"],
            "business_type": profile["business_type"],
            "industry": profile["industry"],
            "created_at": (BASE_TIME - timedelta(days=int(rng.integers(365, 1095)))).isoformat(),
            "is_active": True,
        })
    return merchants


# ─── Generate Customers ────────────────────────────────────────────────────


def generate_customers(merchants: list[dict]) -> list[dict]:
    """
    Generate ~2,000 customers distributed across merchants.
    Customers have correlated attributes.
    """
    customers = []

    for merchant_profile in MERCHANT_PROFILES:
        merchant_id = merchant_profile["id"]
        n_customers = int(NUM_CUSTOMERS * merchant_profile["customer_share"])

        for _ in range(n_customers):
            # Tenure: bimodal — many new + many established
            if rng.random() < 0.3:
                tenure = int(rng.integers(1, 90))  # New customers
            else:
                tenure = int(rng.integers(90, 1460))  # Established

            # Transaction history correlates with tenure
            total_txn = max(1, int(tenure * rng.uniform(0.02, 0.15)))
            success_rate = clamp(0.5 + tenure / 3000 + rng.normal(0, 0.1), 0.2, 0.99)
            successful_txn = max(0, int(total_txn * success_rate))

            # Preferred payment method — weighted
            preferred_pm = rng.choice(
                ["UPI", "CREDIT_CARD", "DEBIT_CARD", "NETBANKING", "WALLET"],
                p=[0.40, 0.20, 0.20, 0.12, 0.08],
            )

            # Days since last purchase correlates with tenure
            days_since = int(rng.integers(0, min(tenure, 180))) if tenure > 0 else 0

            # LTV correlates with tenure and success
            avg_txn_paise = rng.integers(
                merchant_profile["amount_range_paise"][0],
                merchant_profile["amount_range_paise"][1],
            )
            ltv = int(successful_txn * avg_txn_paise * rng.uniform(0.3, 1.0))

            # ~3% opted out
            opted_out = rng.random() < 0.03

            customers.append({
                "id": gen_id("cust"),
                "merchant_id": merchant_id,
                "email": f"customer_{len(customers)}@example.com",
                "phone": f"+91{rng.integers(7000000000, 9999999999)}",
                "name": f"Customer {len(customers)}",
                "customer_tenure_days": tenure,
                "total_transactions": total_txn,
                "successful_transactions": successful_txn,
                "lifetime_value_paise": ltv,
                "preferred_payment_method": preferred_pm,
                "days_since_last_purchase": days_since,
                "opted_out": opted_out,
                "created_at": (BASE_TIME - timedelta(days=tenure)).isoformat(),
            })

    return customers


# ─── Generate Revenue Events ───────────────────────────────────────────────


def generate_events(
    merchants: list[dict],
    customers: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Generate 10,000+ revenue-risk events with all 7 patterns.

    Returns (events, orders).
    """
    events = []
    orders = []

    # Build customer lookup
    customers_by_merchant: dict[str, list[dict]] = {}
    for c in customers:
        customers_by_merchant.setdefault(c["merchant_id"], []).append(c)

    # Track per-customer contact counts for Pattern C
    customer_contact_tracker: dict[str, int] = {}

    # Pre-allocate pattern quotas
    pattern_a_count = 0  # Target: ~2,100 UPI timeouts
    pattern_c_count = 0  # Target: ~500 fatigued customers
    pattern_d_count = 0  # Target: ~200 high-value
    pattern_e_count = 0  # Target: ~800 low-value
    pattern_f_events: list[int] = []  # Target: ~400 systemic cluster
    pattern_g_events: list[int] = []  # Target: ~150 forced failures

    # Systemic degradation window (Pattern F): 10:30PM - 12:30AM IST on day 3
    degradation_start = BASE_TIME + timedelta(days=2, hours=17, minutes=0)  # 10:30PM IST (UTC+5:30)
    degradation_end = BASE_TIME + timedelta(days=2, hours=19, minutes=0)    # 12:30AM IST

    for event_idx in range(NUM_EVENTS):
        # Pick merchant weighted by customer share
        merchant_profile = rng.choice(MERCHANT_PROFILES, p=[m["customer_share"] for m in MERCHANT_PROFILES])
        merchant_id = merchant_profile["id"]
        merchant_customers = customers_by_merchant[merchant_id]

        # Pick customer
        customer = merchant_customers[rng.integers(0, len(merchant_customers))]
        customer_id = customer["id"]

        # Pick event type based on merchant's mix
        event_types = list(merchant_profile["event_mix"].keys())
        event_probs = list(merchant_profile["event_mix"].values())
        event_type = rng.choice(event_types, p=event_probs)

        # ─── Pattern F: Systemic degradation ────────────────────────
        # Force some events into the degradation window with UPI
        is_systemic = False
        if len(pattern_f_events) < 400 and rng.random() < 0.045:
            event_type = "PAYMENT_FAILURE"
            is_systemic = True

        # ─── Amount ─────────────────────────────────────────────────
        lo, hi = merchant_profile["amount_range_paise"]

        # Pattern D: High-value (>₹50,000 = 5,000,000 paise)
        if pattern_d_count < 200 and rng.random() < 0.025:
            amount_paise = int(rng.integers(5_000_000, 25_000_000))
            pattern_d_count += 1
        # Pattern E: Low-value (<₹100 = 10,000 paise)
        elif pattern_e_count < 800 and rng.random() < 0.09:
            amount_paise = int(rng.integers(500, 10_000))
            pattern_e_count += 1
        else:
            # Log-normal distribution for realistic amount spread
            log_mean = np.log(np.sqrt(lo * hi))
            log_std = 0.8
            amount_paise = int(clamp(rng.lognormal(log_mean, log_std), lo, hi))

        # ─── Payment method ─────────────────────────────────────────
        if event_type == "PAYMENT_FAILURE":
            if is_systemic:
                payment_method = "UPI"
            elif rng.random() < 0.45:
                payment_method = "UPI"  # Pattern A: UPI dominant
            else:
                payment_method = rng.choice(
                    ["CREDIT_CARD", "DEBIT_CARD", "NETBANKING", "WALLET", "EMI"],
                    p=[0.25, 0.25, 0.20, 0.15, 0.15],
                )
        elif event_type == "MANDATE_FAILURE":
            payment_method = "NACH"
        elif event_type == "SUBSCRIPTION_FAILURE":
            payment_method = rng.choice(["CREDIT_CARD", "DEBIT_CARD", "UPI", "NACH"], p=[0.35, 0.25, 0.25, 0.15])
        else:
            payment_method = customer["preferred_payment_method"]

        # ─── Failure reason ─────────────────────────────────────────
        if event_type == "PAYMENT_FAILURE":
            reasons_for_method = FAILURE_REASONS["PAYMENT_FAILURE"].get(payment_method, ["UNKNOWN_ERROR"])
            # Pattern A: Bias toward UPI_TIMEOUT
            if payment_method == "UPI" and rng.random() < 0.55:
                failure_reason = "UPI_TIMEOUT"
                pattern_a_count += 1
            else:
                failure_reason = rng.choice(reasons_for_method)
        elif event_type in FAILURE_REASONS:
            reasons_list = FAILURE_REASONS[event_type]
            failure_reason = rng.choice(reasons_list)
        else:
            failure_reason = "UNKNOWN"

        # ─── Timestamp ──────────────────────────────────────────────
        if is_systemic:
            # Pattern F: Cluster in degradation window
            offset_hours = rng.uniform(0, (degradation_end - degradation_start).total_seconds() / 3600)
            timestamp = degradation_start + timedelta(hours=offset_hours)
        elif payment_method == "UPI" and event_type == "PAYMENT_FAILURE" and rng.random() < 0.35:
            # Pattern A: UPI timeouts concentrated 10PM-12AM IST
            day_offset = rng.integers(0, EVENT_WINDOW_DAYS)
            hour_offset = rng.uniform(16.5, 18.5)  # 10PM-12AM IST in UTC
            timestamp = BASE_TIME + timedelta(days=int(day_offset), hours=hour_offset)
        else:
            timestamp = gen_timestamp(BASE_TIME, (0, EVENT_WINDOW_DAYS * 24))

        # ─── Attempt count ──────────────────────────────────────────
        # More attempts for payment failures, fewer for abandonment
        if event_type in ("PAYMENT_FAILURE", "SUBSCRIPTION_FAILURE", "MANDATE_FAILURE"):
            attempt_count = int(rng.choice([0, 1, 1, 2, 2, 3, 4, 5], p=[0.15, 0.30, 0.20, 0.15, 0.10, 0.05, 0.03, 0.02]))
        elif event_type == "CHECKOUT_ABANDONMENT":
            attempt_count = 0
        else:
            attempt_count = int(rng.integers(0, 3))

        # ─── Previous success / recovery success ────────────────────
        # Pattern B: Customers with prev UPI success
        previous_success = customer["successful_transactions"] > 0
        if payment_method == "UPI" and customer["preferred_payment_method"] == "UPI":
            previous_success = True  # Pattern B: explicitly mark

        previous_recovery_success = (
            previous_success
            and customer["successful_transactions"] > 3
            and rng.random() < 0.3
        )

        # ─── Contact tracking (Pattern C) ───────────────────────────
        contact_count = customer_contact_tracker.get(customer_id, 0)

        # Pattern C: Some customers get many contacts
        if pattern_c_count < 500 and contact_count == 0 and rng.random() < 0.06:
            contact_count = int(rng.integers(3, 8))
            pattern_c_count += 1
        elif contact_count == 0 and rng.random() < 0.25:
            contact_count = int(rng.integers(1, 3))

        customer_contact_tracker[customer_id] = contact_count

        if contact_count > 0:
            last_contact_hours = float(rng.uniform(1, 72))
            if contact_count >= 3:
                last_contact_hours = float(rng.uniform(1, 24))  # Recent contacts for fatigued
        else:
            last_contact_hours = None

        # ─── Customer intent score ──────────────────────────────────
        # Correlated with: tenure, recent activity, previous success, attempt count
        base_intent = 0.5

        # Tenure boost
        if customer["customer_tenure_days"] > 365:
            base_intent += 0.15
        elif customer["customer_tenure_days"] > 90:
            base_intent += 0.08

        # Recent activity boost
        if customer["days_since_last_purchase"] is not None and customer["days_since_last_purchase"] < 14:
            base_intent += 0.12

        # Previous success boost
        if previous_success:
            base_intent += 0.10

        # Attempt penalty
        base_intent -= attempt_count * 0.06

        # Event type adjustment
        if event_type == "CHECKOUT_ABANDONMENT":
            base_intent -= 0.10  # Lower intent — didn't even attempt payment
        elif event_type == "OVERDUE_RECEIVABLE":
            base_intent -= 0.15
        elif event_type == "SUBSCRIPTION_FAILURE":
            base_intent += 0.05  # Existing subscriber — likely wants service

        # Contact fatigue penalty
        if contact_count >= 3:
            base_intent -= 0.15

        # Noise
        intent_score = clamp(base_intent + rng.normal(0, 0.08))

        # ─── Event-specific fields ──────────────────────────────────
        cart_value_paise = None
        subscription_plan = None
        invoice_age_days = None

        if event_type == "CHECKOUT_ABANDONMENT":
            cart_value_paise = amount_paise  # Cart value = event amount
        elif event_type == "SUBSCRIPTION_FAILURE":
            subscription_plan = rng.choice(SUBSCRIPTION_PLANS)
        elif event_type == "OVERDUE_RECEIVABLE":
            invoice_age_days = int(rng.choice([15, 30, 45, 60, 90, 120], p=[0.15, 0.30, 0.25, 0.15, 0.10, 0.05]))
            if "OVERDUE_90" in failure_reason:
                invoice_age_days = int(rng.integers(90, 150))

        # ─── Eligibility ────────────────────────────────────────────
        eligible = True
        if customer["opted_out"]:
            eligible = False
        elif amount_paise <= 0:
            eligible = False

        # ─── Pattern G: Force execution failures ────────────────────
        pattern_flags: dict[str, Any] = {}
        if is_systemic:
            pattern_flags["systemic_degradation"] = True
            pattern_f_events.append(event_idx)

        if len(pattern_g_events) < 150 and rng.random() < 0.018:
            pattern_flags["force_fallback"] = True
            pattern_g_events.append(event_idx)

        if amount_paise >= 5_000_000:
            pattern_flags["high_value"] = True

        if amount_paise < 10_000:
            pattern_flags["low_value"] = True

        if contact_count >= 3:
            pattern_flags["high_fatigue"] = True

        if previous_success and payment_method == "UPI":
            pattern_flags["previous_upi_success"] = True

        # ─── Create order ───────────────────────────────────────────
        order_id = gen_id("ord")
        order_status = "failed" if event_type == "PAYMENT_FAILURE" else (
            "abandoned" if event_type == "CHECKOUT_ABANDONMENT" else "created"
        )
        orders.append({
            "id": order_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "amount_paise": amount_paise,
            "currency": "INR",
            "status": order_status,
            "created_at": timestamp.isoformat(),
        })

        # ─── Create event ───────────────────────────────────────────
        events.append({
            "id": gen_id("evt"),
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "order_id": order_id,
            "event_type": event_type,
            "amount_paise": amount_paise,
            "currency": "INR",
            "timestamp": timestamp.isoformat(),
            "payment_method": payment_method,
            "failure_reason": failure_reason,
            "attempt_count": attempt_count,
            "previous_success": previous_success,
            "previous_recovery_success": previous_recovery_success,
            "previous_contact_count": contact_count,
            "last_contact_hours_ago": last_contact_hours,
            "customer_tenure_days": customer["customer_tenure_days"],
            "days_since_last_purchase": customer["days_since_last_purchase"],
            "cart_value_paise": cart_value_paise,
            "subscription_plan": subscription_plan,
            "invoice_age_days": invoice_age_days,
            "customer_intent_score": round(intent_score, 4),
            "eligible_for_recovery": eligible,
            "pattern_flags": pattern_flags if pattern_flags else None,
            "created_at": timestamp.isoformat(),
        })

    return events, orders


# ─── Summary Statistics ─────────────────────────────────────────────────────


def print_summary(events: list[dict], customers: list[dict]):
    """Print summary statistics for the generated dataset."""
    df = pd.DataFrame(events)

    total_amount = df["amount_paise"].sum()
    eligible_df = df[df["eligible_for_recovery"] == True]

    print("\n" + "=" * 60)
    print("  RecoverOS — Synthetic Dataset Summary")
    print("=" * 60)
    print(f"\n  Total events:          {len(df):,}")
    print(f"  Total customers:       {len(customers):,}")
    print(f"  Revenue at risk:       ₹{total_amount / 100:,.2f}")
    print(f"  Eligible for recovery: {len(eligible_df):,}")

    print(f"\n  ── Event Type Distribution ──")
    for et, count in df["event_type"].value_counts().items():
        pct = count / len(df) * 100
        amt = df[df["event_type"] == et]["amount_paise"].sum() / 100
        print(f"    {et:30s}  {count:5,}  ({pct:5.1f}%)  ₹{amt:>12,.2f}")

    print(f"\n  ── Payment Method Distribution ──")
    for pm, count in df["payment_method"].value_counts().items():
        print(f"    {pm:20s}  {count:5,}")

    print(f"\n  ── Pattern Verification ──")
    upi_timeouts = len(df[(df["payment_method"] == "UPI") & (df["failure_reason"] == "UPI_TIMEOUT")])
    print(f"    Pattern A (UPI timeouts):          {upi_timeouts:,}")

    prev_upi = len(df[df["pattern_flags"].apply(lambda x: x.get("previous_upi_success", False) if isinstance(x, dict) else False)])
    print(f"    Pattern B (prev UPI success):       {prev_upi:,}")

    fatigued = len(df[df["previous_contact_count"] >= 3])
    print(f"    Pattern C (high fatigue):           {fatigued:,}")

    high_val = len(df[df["amount_paise"] >= 5_000_000])
    print(f"    Pattern D (high-value >₹50K):      {high_val:,}")

    low_val = len(df[df["amount_paise"] < 10_000])
    print(f"    Pattern E (low-value <₹100):       {low_val:,}")

    systemic = len(df[df["pattern_flags"].apply(lambda x: x.get("systemic_degradation", False) if isinstance(x, dict) else False)])
    print(f"    Pattern F (systemic degradation):   {systemic:,}")

    fallback = len(df[df["pattern_flags"].apply(lambda x: x.get("force_fallback", False) if isinstance(x, dict) else False)])
    print(f"    Pattern G (force fallback):         {fallback:,}")

    print(f"\n  ── Correlation Checks ──")
    low_attempt = df[df["attempt_count"] <= 1]["customer_intent_score"].mean()
    high_attempt = df[df["attempt_count"] >= 3]["customer_intent_score"].mean()
    print(f"    Mean intent (attempts ≤ 1):  {low_attempt:.3f}")
    print(f"    Mean intent (attempts ≥ 3):  {high_attempt:.3f}")
    print(f"    → {'✓' if low_attempt > high_attempt else '✗'} Higher intent with fewer attempts")

    new_cust = df[df["customer_tenure_days"] < 90]["customer_intent_score"].mean()
    old_cust = df[df["customer_tenure_days"] > 365]["customer_intent_score"].mean()
    print(f"    Mean intent (tenure < 90d):  {new_cust:.3f}")
    print(f"    Mean intent (tenure > 365d): {old_cust:.3f}")
    print(f"    → {'✓' if old_cust > new_cust else '✗'} Higher intent with longer tenure")

    opted_out = len(df[df["eligible_for_recovery"] == False])
    print(f"\n    Ineligible (opted out etc.): {opted_out:,}")

    print("\n" + "=" * 60)


# ─── Save to Files ──────────────────────────────────────────────────────────


def save_dataset(merchants, customers, orders, events):
    """Save generated data as JSON files."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    datasets = {
        "merchants.json": merchants,
        "customers.json": customers,
        "orders.json": orders,
        "revenue_events.json": events,
    }

    for filename, data in datasets.items():
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"  Saved {filename:25s}  ({len(data):,} records)")

    print(f"\n  Output directory: {OUTPUT_DIR}")


# ─── Main ───────────────────────────────────────────────────────────────────


def main():
    print("\nRecoverOS — Generating synthetic dataset...\n")

    merchants = generate_merchants()
    print(f"  Generated {len(merchants)} merchants")

    customers = generate_customers(merchants)
    print(f"  Generated {len(customers):,} customers")

    events, orders = generate_events(merchants, customers)
    print(f"  Generated {len(events):,} revenue events")
    print(f"  Generated {len(orders):,} orders")

    print_summary(events, customers)

    save_dataset(merchants, customers, orders, events)

    print("\n✓ Data generation complete.\n")
    return merchants, customers, orders, events


if __name__ == "__main__":
    main()
