"""SQLAlchemy ORM models for RecoverOS."""

import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from apps.api.database import Base


class BaseORM(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# Enums
class EventType(str, Enum):
    """Types of revenue events."""
    PAYMENT_FAILURE = "PAYMENT_FAILURE"
    CHECKOUT_ABANDONMENT = "CHECKOUT_ABANDONMENT"
    SUBSCRIPTION_FAILURE = "SUBSCRIPTION_FAILURE"
    MANDATE_FAILURE = "MANDATE_FAILURE"
    OVERDUE_RECEIVABLE = "OVERDUE_RECEIVABLE"


class PaymentMethod(str, Enum):
    """Payment methods."""
    UPI = "UPI"
    CARD = "CARD"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"


# Models
class Merchant(BaseORM):
    """Merchant table."""
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    business_type: Mapped[str] = mapped_column(String(100))
    industry: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class Customer(BaseORM):
    """Customer table."""
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_tenure_days: Mapped[int] = mapped_column(Integer, default=0)
    total_transactions: Mapped[int] = mapped_column(Integer, default=0)
    successful_transactions: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_value_paise: Mapped[int] = mapped_column(Integer, default=0)
    preferred_payment_method: Mapped[Optional[PaymentMethod]] = mapped_column(SQLEnum(PaymentMethod), nullable=True)
    days_since_last_purchase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    merchant: Mapped["Merchant"] = relationship("Merchant")


class Order(BaseORM):
    """Order table."""
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    amount_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    merchant: Mapped["Merchant"] = relationship("Merchant")
    customer: Mapped["Customer"] = relationship("Customer")


class RevenueEvent(BaseORM):
    """Revenue event table."""
    __tablename__ = "revenue_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    order_id: Mapped[Optional[str]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    event_type: Mapped[EventType] = mapped_column(SQLEnum(EventType))
    amount_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime)
    payment_method: Mapped[Optional[PaymentMethod]] = mapped_column(SQLEnum(PaymentMethod), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    previous_success: Mapped[bool] = mapped_column(Boolean, default=False)
    previous_recovery_success: Mapped[bool] = mapped_column(Boolean, default=False)
    previous_contact_count: Mapped[int] = mapped_column(Integer, default=0)
    last_contact_hours_ago: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    customer_tenure_days: Mapped[int] = mapped_column(Integer, default=0)
    days_since_last_purchase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cart_value_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    subscription_plan: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    invoice_age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    customer_intent_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eligible_for_recovery: Mapped[bool] = mapped_column(Boolean, default=True)
    pattern_flags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    merchant: Mapped["Merchant"] = relationship("Merchant")
    customer: Mapped["Customer"] = relationship("Customer")
    order: Mapped[Optional["Order"]] = relationship("Order")

    __table_args__ = (
        Index("idx_event_type", "event_type"),
        Index("idx_payment_method", "payment_method"),
        Index("idx_timestamp", "timestamp"),
        Index("idx_eligible_for_recovery", "eligible_for_recovery"),
        Index("idx_amount", "amount_paise"),
    )


class RecoveryOpportunity(BaseORM):
    """Recovery opportunity table."""
    __tablename__ = "recovery_opportunities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    revenue_event_id: Mapped[str] = mapped_column(ForeignKey("revenue_events.id"))
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    recovery_probability: Mapped[float] = mapped_column(Float)
    estimated_recovery_amount_paise: Mapped[int] = mapped_column(Integer)
    eligible_for_recovery: Mapped[bool] = mapped_column(Boolean, default=True)
    priority_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    revenue_event: Mapped["RevenueEvent"] = relationship("RevenueEvent")


class RecoveryPrediction(BaseORM):
    """Recovery prediction table."""
    __tablename__ = "recovery_predictions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("recovery_opportunities.id"))
    model_version: Mapped[str] = mapped_column(String(50))
    prediction: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    features_used: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class RecoveryDecision(BaseORM):
    """Recovery decision table."""
    __tablename__ = "recovery_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("recovery_opportunities.id"))
    decision_type: Mapped[str] = mapped_column(String(50))
    action_type: Mapped[str] = mapped_column(String(50))
    amount_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class RecoveryAction(BaseORM):
    """Recovery action table."""
    __tablename__ = "recovery_actions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("recovery_decisions.id"))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("recovery_opportunities.id"))
    action_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    scheduled_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    executed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class ActionAttempt(BaseORM):
    """Action attempt table."""
    __tablename__ = "action_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("recovery_actions.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50))
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class RecoveryOutcome(BaseORM):
    """Recovery outcome table."""
    __tablename__ = "recovery_outcomes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("recovery_actions.id"))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("recovery_opportunities.id"))
    recovered_amount_paise: Mapped[int] = mapped_column(Integer)
    outcome_type: Mapped[str] = mapped_column(String(50))
    recorded_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class ControlGroup(BaseORM):
    """Control group table."""
    __tablename__ = "control_groups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("recovery_opportunities.id"))
    group_type: Mapped[str] = mapped_column(String(50))
    assigned_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class AuditEvent(BaseORM):
    """Audit event table."""
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50))
    actor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class BusinessPolicy(BaseORM):
    """Business policy table."""
    __tablename__ = "business_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    policy_name: Mapped[str] = mapped_column(String(255))
    policy_key: Mapped[str] = mapped_column(String(100))
    policy_value: Mapped[str] = mapped_column(String(255))
    policy_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    merchant: Mapped["Merchant"] = relationship("Merchant")
