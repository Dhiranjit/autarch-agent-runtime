"""Database entities using SQLModel."""

import uuid
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel

from app.core.models import ApprovalStatus, TaskStatus


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        index=True,
    )
    source_type: str = Field(default="email")
    status: TaskStatus = Field(default=TaskStatus.PENDING, index=True)
    context_json: str = Field(default="{}")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Approval(SQLModel, table=True):
    __tablename__ = "approvals"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        index=True,
    )
    task_id: str = Field(foreign_key="tasks.id", index=True)
    tool_name: str
    proposed_args_json: str = Field(default="{}")
    edited_args_json: str | None = Field(default=None)
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, index=True)
    resolved_by: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    resolved_at: datetime | None = Field(default=None)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        index=True,
    )
    task_id: str | None = Field(default=None, foreign_key="tasks.id", index=True)
    approval_id: str | None = Field(default=None, foreign_key="approvals.id", index=True)
    event_type: str = Field(index=True)
    tool_name: str | None = Field(default=None)
    risk_level: int | None = Field(default=None)
    policy_decision: str | None = Field(default=None)
    actor: str = Field(default="system")
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

