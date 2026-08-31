"""
RecoverOS — Database Seeder

Loads generated JSON data and seeds the PostgreSQL database.
Idempotent: truncates tables before inserting.
"""

import json
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from apps.api.database import get_engine, get_db_session, Base
from apps.api.models.tables import (
    Merchant, Customer, Order, RevenueEvent, BusinessPolicy,
    EventType, PaymentMethod,
)

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "dataset")


def load_json(filename: str) -> list[dict]:
    """Load a JSON data file."""
    filepath = os.path.join(DATASET_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  ✗ File not found: {filepath}")
        print("  Run 'python scripts/generate_data.py' first.")
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def truncate_tables(session):
    """Truncate all tables (cascade) for idempotent seeding."""
    tables = [
        "audit_events", "control_groups", "recovery_outcomes",
        "action_attempts", "recovery_actions", "recovery_decisions",
        "recovery_predictions", "recovery_opportunities",
        "revenue_events", "orders", "business_policies",
        "customers", "merchants",
    ]
    for table in tables:
        session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
    session.commit()
    print("  Truncated all tables.")


def seed_merchants(session, data: list[dict]):
    """Seed merchants table."""
    for row in data:
        merchant = Merchant(
            id=row["id"],
            name=row["name"],
            business_type=row["business_type"],
            industry=row["industry"],
            is_active=row["is_active"],
        )
        session.add(merchant)
    session.flush()
    print(f"  ✓ Seeded {len(data):,} merchants")


def seed_customers(session, data: list[dict]):
    """Seed customers table."""
    for row in data:
        pm = row.get("preferred_payment_method")
        customer = Customer(
            id=row["id"],
            merchant_id=row["merchant_id"],
            email=row.get("email"),
            phone=row.get("phone"),
            name=row.get("name"),
            customer_tenure_days=row.get("customer_tenure_days", 0),
            total_transactions=row.get("total_transactions", 0),
            successful_transactions=row.get("successful_transactions", 0),
            lifetime_value_paise=row.get("lifetime_value_paise", 0),
            preferred_payment_method=PaymentMethod(pm) if pm else None,
            days_since_last_purchase=row.get("days_since_last_purchase"),
            opted_out=row.get("opted_out", False),
        )
        session.add(customer)
    session.flush()
    print(f"  ✓ Seeded {len(data):,} customers")


def seed_orders(session, data: list[dict]):
    """Seed orders table in batches."""
    batch_size = 1000
    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        for row in batch:
            order = Order(
                id=row["id"],
                merchant_id=row["merchant_id"],
                customer_id=row["customer_id"],
                amount_paise=row["amount_paise"],
                currency=row.get("currency", "INR"),
                status=row["status"],
            )
            session.add(order)
        session.flush()
    print(f"  ✓ Seeded {len(data):,} orders")


def seed_events(session, data: list[dict]):
    """Seed revenue_events table in batches."""
    batch_size = 1000
    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        for row in batch:
            pm = row.get("payment_method")
            event = RevenueEvent(
                id=row["id"],
                merchant_id=row["merchant_id"],
                customer_id=row["customer_id"],
                order_id=row.get("order_id"),
                event_type=EventType(row["event_type"]),
                amount_paise=row["amount_paise"],
                currency=row.get("currency", "INR"),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                payment_method=PaymentMethod(pm) if pm else None,
                failure_reason=row.get("failure_reason"),
                attempt_count=row.get("attempt_count", 0),
                previous_success=row.get("previous_success", False),
                previous_recovery_success=row.get("previous_recovery_success", False),
                previous_contact_count=row.get("previous_contact_count", 0),
                last_contact_hours_ago=row.get("last_contact_hours_ago"),
                customer_tenure_days=row.get("customer_tenure_days", 0),
                days_since_last_purchase=row.get("days_since_last_purchase"),
                cart_value_paise=row.get("cart_value_paise"),
                subscription_plan=row.get("subscription_plan"),
                invoice_age_days=row.get("invoice_age_days"),
                customer_intent_score=row.get("customer_intent_score"),
                eligible_for_recovery=row.get("eligible_for_recovery", True),
                pattern_flags=row.get("pattern_flags"),
            )
            session.add(event)
        session.flush()
    print(f"  ✓ Seeded {len(data):,} revenue events")


def seed_default_policies(session, merchant_ids: list[str]):
    """Seed default business policies for each merchant."""
    default_policies = [
        ("max_automated_actions_per_day", "300", "integer", "Maximum automated recovery actions per day"),
        ("max_contacts_per_customer_per_day", "2", "integer", "Maximum contacts per customer per day"),
        ("max_auto_action_amount_paise", "5000000", "integer", "Maximum amount for automatic action (₹50,000)"),
        ("discount_budget_paise", "2500000", "integer", "Daily discount/incentive budget (₹25,000)"),
        ("min_auto_recovery_probability", "0.70", "float", "Minimum probability for automatic recovery"),
        ("high_value_threshold_paise", "5000000", "integer", "Amount above which human approval required"),
        ("max_retry_count", "3", "integer", "Maximum retry attempts per action"),
        ("contact_cooldown_hours", "4", "integer", "Minimum hours between customer contacts"),
    ]

    count = 0
    for merchant_id in merchant_ids:
        for key, value, ptype, desc in default_policies:
            policy = BusinessPolicy(
                id=f"pol_{merchant_id}_{key}",
                merchant_id=merchant_id,
                policy_name=key.replace("_", " ").title(),
                policy_key=key,
                policy_value=value,
                policy_type=ptype,
                description=desc,
                is_active=True,
            )
            session.add(policy)
            count += 1
    session.flush()
    print(f"  ✓ Seeded {count} business policies")


def verify_counts(session):
    """Verify row counts after seeding."""
    tables = ["merchants", "customers", "orders", "revenue_events", "business_policies"]
    print("\n  ── Row Counts ──")
    for table in tables:
        result = session.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
        count = result.scalar()
        print(f"    {table:25s}  {count:,}")


def main():
    print("\nRecoverOS — Seeding database...\n")

    # Load data
    merchants_data = load_json("merchants.json")
    customers_data = load_json("customers.json")
    orders_data = load_json("orders.json")
    events_data = load_json("revenue_events.json")

    print(f"  Loaded {len(merchants_data)} merchants, {len(customers_data):,} customers,")
    print(f"         {len(orders_data):,} orders, {len(events_data):,} events\n")

    with get_db_session() as session:
        # Truncate for idempotency
        truncate_tables(session)

        # Seed in dependency order
        seed_merchants(session, merchants_data)
        seed_customers(session, customers_data)
        seed_orders(session, orders_data)
        seed_events(session, events_data)

        merchant_ids = [m["id"] for m in merchants_data]
        seed_default_policies(session, merchant_ids)

        # Commit
        session.commit()

        # Verify
        verify_counts(session)

    print("\n✓ Database seeding complete.\n")


if __name__ == "__main__":
    main()
