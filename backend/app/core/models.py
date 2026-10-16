"""Core domain models, enums, and schemas."""

from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any
from pydantic import BaseModel, Field


class RiskLevel(IntEnum):
    LEVEL_0 = 0  # Read-only
    LEVEL_1 = 1  # Stage / Prepare (non-external)
    LEVEL_2 = 2  # Internal state mutation (e.g. create_task)
    LEVEL_3 = 3  # External side effect (e.g. send_email)


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class ApprovalResolution(str, Enum):
    APPROVE = "APPROVE"
    EDIT = "EDIT"
    REJECT = "REJECT"


class ExecutionContext(BaseModel):
    trigger_type: str = "email"
    source_sender: str
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionProposal(BaseModel):
    tool_name: str
    args: dict[str, Any]
    risk_level: RiskLevel
    reasoning: str = ""


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool
    risk_level: RiskLevel
    reason: str


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None


class SanitizedEmail(BaseModel):
    sender: str
    recipient: str = ""
    subject: str
    clean_body: str
    thread_id: str | None = None


class TriageResult(BaseModel):
    summary: str
    proposals: list[ActionProposal] = Field(default_factory=list)


class EventEnvelope(BaseModel):
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

