"""
RecoverOS — Table creation script.

Creates all database tables from SQLAlchemy ORM models.
Safe to re-run: uses create_all (idempotent).
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from apps.api.database import get_engine
from apps.api.models.tables import (  # noqa: F401 — import to register models
    Merchant, Customer, Order, RevenueEvent,
    RecoveryOpportunity, RecoveryPrediction, RecoveryDecision,
    RecoveryAction, ActionAttempt, RecoveryOutcome,
    ControlGroup, AuditEvent, BusinessPolicy,
    BaseORM as Base,
)


def create_tables():
    """Create all tables in the database."""
    engine = get_engine()
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print(f"Created {len(Base.metadata.tables)} tables:")
    for table_name in sorted(Base.metadata.tables.keys()):
        print(f"  ✓ {table_name}")
    print("\nDone.")


def drop_tables():
    """Drop all tables (destructive — use with caution)."""
    engine = get_engine()
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--drop":
        drop_tables()
    create_tables()
