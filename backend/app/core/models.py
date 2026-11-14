"""Core domain models: enums and schemas."""
import secrets
from typing import Any
from enum import IntEnum, StrEnum
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class RiskLevel(IntEnum):
    LEVEL_0 = 0  # Read-only
    LEVEL_1 = 1  # Stage / Prepare
    LEVEL_2 = 2  # Internal state mutation (e.g. create_task)
    LEVEL_3 = 3  # External side effect (e.g. send_email)
    LEVEL_4 = 4  # Payment Permission


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CHILDREN = "WAITING_CHILDREN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExecutionMode(StrEnum):
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"    # Awaiting human or policy decision
    APPROVED = "APPROVED"  # Permission Granted
    REJECTED = "REJECTED"  # Permission denied


class UserApprovalAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"                       # Auto-approved (execute internally)
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL" # Needs human approval
    DENY = "DENY"  


class ProposedToolCall(BaseModel):
    id: str = Field(default_factory=lambda: f"tool_call_{secrets.token_hex(4)}")
    tool_name: str
    args: dict[str, Any]
    reasoning: str = ""


class SubTask(BaseModel):
    execution_mode: ExecutionMode
    static_module: str | None = None
    skill_name: str | None = None
    step_order: int = 0
    context: str = ""


class AgentResponse(BaseModel):
    message: str = ""
    proposed_tool_calls: list[ProposedToolCall] = Field(default_factory=list)
    subtasks: list[SubTask] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    tool_call_id: str
    tool_name: str
    action: PolicyAction
    reason: str = ""


class ToolResult(BaseModel):
    tool_call_id: str
    tool_name: str
    success: bool
    output: Any = None


class EventEnvelope(BaseModel):
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))