"""Core domain models: enums and schemas."""

from datetime import datetime, timezone
from enum import IntEnum, StrEnum
import secrets
from typing import Any
from pydantic import BaseModel, Field


class RiskLevel(IntEnum):
    LEVEL_0 = 0  # Read-only
    LEVEL_1 = 1  # Stage / Prepare
    LEVEL_2 = 2  # Internal state mutation (e.g. create_todo)
    LEVEL_3 = 3  # External side effect (e.g. send_email)
    LEVEL_4 = 4  # Payment Permission


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"    # Awaiting human or policy decision
    APPROVED = "APPROVED"  # Permission granted
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


class AgentProfile(BaseModel):
    """Configuration for an orchestrator or specialized subagent."""

    name: str
    description: str
    system_prompt: str
    max_steps: int = 8


class EventEnvelope(BaseModel):
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
