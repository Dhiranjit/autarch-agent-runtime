"""Tool definitions grouped by domain and predefined workflows."""

from pydantic import BaseModel

from app.core.models import RiskLevel
from app.features.email_triage import build_ingest_emails_tool
from app.tools.builtin import mock_email_provider, mock_task_provider
from app.tools.registry import Tool


# --- Task tools ---

class CreateTaskArgs(BaseModel):
    title: str
    description: str = ""

    model_config = {"extra": "ignore"}


create_task_tool = Tool(
    name="create_task",
    description="Create an internal task item (Level 2).",
    parameters=CreateTaskArgs,
    risk_level=RiskLevel.LEVEL_2,
    func=mock_task_provider.create_task,
)

TASK_TOOLS: list[Tool] = [create_task_tool]


# --- Email tools & Predefined Workflows ---

ingest_emails_tool = build_ingest_emails_tool()


class SendEmailArgs(BaseModel):
    to: str
    subject: str
    body: str

    model_config = {"extra": "ignore"}


send_email_tool = Tool(
    name="send_email",
    description="Send an outbound email (Level 3 - requires human approval).",
    parameters=SendEmailArgs,
    risk_level=RiskLevel.LEVEL_3,
    func=mock_email_provider.send_email,
)

EMAIL_TOOLS: list[Tool] = [ingest_emails_tool, send_email_tool]


# --- Aggregated tools ---

ALL_TOOLS: list[Tool] = [
    *TASK_TOOLS,
    *EMAIL_TOOLS,
]
