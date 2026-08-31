"""
RecoverOS — Incrementality Control Group Manager

Splits new opportunities into Treatment (A) vs Control (B) groups
to allow rigorous measurement of recovery lift.
"""

import uuid
import hashlib
from sqlalchemy.orm import Session

from apps.api.models.tables import RevenueEvent, ControlGroup, ControlGroupType


def assign_control_group(db: Session, event: RevenueEvent) -> ControlGroup:
    """
    Assigns a revenue event to either TREATMENT or CONTROL using a deterministic
    hash of the event ID to maintain a stable 50/50 split.
    """
    # Check if already assigned
    existing = db.query(ControlGroup).filter(ControlGroup.event_id == event.id).first()
    if existing:
        return existing

    # Deterministic split: hash event ID and check modulo 2
    hasher = hashlib.md5(event.id.encode('utf-8'))
    hash_val = int(hasher.hexdigest(), 16)
    group_type = ControlGroupType.CONTROL if hash_val % 2 == 0 else ControlGroupType.TREATMENT

    control_assignment = ControlGroup(
        id=f"cg_{uuid.uuid4().hex[:12]}",
        event_id=event.id,
        group_type=group_type,
        recovered=False,
        recovered_amount_paise=0,
    )
    
    db.add(control_assignment)
    return control_assignment


def is_treatment_group(db: Session, event_id: str) -> bool:
    """Check if an event belongs to the Treatment group."""
    assignment = db.query(ControlGroup).filter(ControlGroup.event_id == event_id).first()
    if not assignment:
        return True  # Default to Treatment if unassigned
    return assignment.group_type == ControlGroupType.TREATMENT
