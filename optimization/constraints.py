"""
RecoverOS — Optimization Constraints

Tracks capacity, budget consumption, and policy limits for portfolio allocation.
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session

from apps.api.models.tables import BusinessPolicy, ActionType


class AllocationConstraints:
    def __init__(self, db: Session, merchant_id: str):
        self.db = db
        self.merchant_id = merchant_id
        
        # Load policies
        self.policies = self._load_policies()
        
        # Core limits
        self.max_automated_actions = int(self.policies.get("max_automated_actions_per_day", 300))
        self.max_contacts_per_customer = int(self.policies.get("max_contacts_per_customer_per_day", 2))
        self.max_auto_action_amount = int(self.policies.get("max_auto_action_amount_paise", 5000000))
        self.discount_budget_remaining = int(self.policies.get("discount_budget_paise", 2500000))
        self.min_probability = float(self.policies.get("min_auto_recovery_probability", 0.70))
        self.high_value_threshold = int(self.policies.get("high_value_threshold_paise", 5000000))
        self.contact_cooldown_hours = int(self.policies.get("contact_cooldown_hours", 4))

        # Consumption state (to track usage during current day's allocation run)
        self.automated_actions_count = 0
        self.total_discount_spent = 0
        
        # Customer-specific contact counts in this run
        self.customer_run_contacts: Dict[str, int] = {}

    def _load_policies(self) -> Dict[str, Any]:
        """Load business policies for the merchant from the database."""
        policies = {}
        query = self.db.query(BusinessPolicy).filter(
            BusinessPolicy.merchant_id == self.merchant_id,
            BusinessPolicy.is_active == True
        )

        rows = query.all() if hasattr(query, "all") else []
        if not rows and hasattr(query, "first"):
            first = query.first()
            if first is not None:
                rows = [first]

        for r in rows:
            if r is None:
                continue
            val = r.policy_value
            if r.policy_type == "integer":
                policies[r.policy_key] = int(val)
            elif r.policy_type == "float":
                policies[r.policy_key] = float(val)
            elif r.policy_type == "boolean":
                if isinstance(val, bool):
                    policies[r.policy_key] = val
                else:
                    policies[r.policy_key] = str(val).lower() == "true"
            else:
                policies[r.policy_key] = val
        return policies

    def can_allocate_automated_action(self, customer_id: str, amount_paise: int, probability: float) -> bool:
        """
        Check if we can schedule an automated action based on policy constraints.
        Does not apply to HUMAN_REVIEW (which requires manual review).
        """
        # Daily action capacity limit
        if self.automated_actions_count >= self.max_automated_actions:
            return False

        # Minimum probability rule
        if probability < self.min_probability:
            return False

        # Customer daily contact limit check
        contacts_in_run = self.customer_run_contacts.get(customer_id, 0)
        if contacts_in_run >= self.max_contacts_per_customer:
            return False

        # High-value auto-action threshold rule
        if amount_paise > self.max_auto_action_amount:
            return False

        return True

    def consume_action(self, customer_id: str, incentive_cost_paise: int = 0):
        """Consume action capacity and discount budget."""
        incentive_cost_paise = incentive_cost_paise or 0
        self.automated_actions_count += 1
        self.total_discount_spent += incentive_cost_paise
        self.customer_run_contacts[customer_id] = self.customer_run_contacts.get(customer_id, 0) + 1
        self.discount_budget_remaining -= incentive_cost_paise
