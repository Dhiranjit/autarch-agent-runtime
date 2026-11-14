"""Database entities using SQLModel."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, Relationship, SQLModel

from app.core.models import ApprovalStatus, ExecutionMode, TaskStatus


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        index=True,
    )
    parent_task_id: str | None = Field(
        default=None,
        foreign_key="tasks.id",
        index=True,
    )
    root_task_id: str | None = Field(default=None, index=True)
    step_order: int = Field(default=0, index=True)
    execution_mode: ExecutionMode = Field(default=ExecutionMode.DYNAMIC)
    static_module: str | None = Field(default=None)
    skill_name: str | None = Field(default=None)
    source_type: str = Field(default="email")
    status: TaskStatus = Field(default=TaskStatus.QUEUED, index=True)
    context_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    parent: Optional["Task"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={
            "remote_side": "Task.id",
            "foreign_keys": "[Task.parent_task_id]",
        },
    )
    children: list["Task"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={
            "foreign_keys": "[Task.parent_task_id]",
        },
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

