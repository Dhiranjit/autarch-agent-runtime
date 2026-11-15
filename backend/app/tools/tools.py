"""Tool definitions grouped by domain and predefined workflows."""

from pydantic import BaseModel

from app.core.models import RiskLevel
from app.features.email_triage import build_ingest_emails_tool
from app.tools.builtin import mock_email_provider, todo_provider
from app.tools.registry import Tool


# --- Todo tools ---

class CreateTodoArgs(BaseModel):
    title: str
    description: str = ""

    model_config = {"extra": "ignore"}


class ListTodosArgs(BaseModel):
    include_completed: bool = False

    model_config = {"extra": "ignore"}


create_todo_tool = Tool(
    name="create_todo",
    description="Save a permanent user to-do / reminder item in the Todo list (Level 2).",
    parameters=CreateTodoArgs,
    risk_level=RiskLevel.LEVEL_2,
    func=todo_provider.create_todo,
)

list_todos_tool = Tool(
    name="list_todos",
    description="Read saved items from the permanent Todo list (Level 0).",
    parameters=ListTodosArgs,
    risk_level=RiskLevel.LEVEL_0,
    func=todo_provider.list_todos,
)

TODO_TOOLS: list[Tool] = [create_todo_tool, list_todos_tool]


# --- Email tools & Predefined Workflows ---

ingest_emails_tool = build_ingest_emails_tool()


class SendEmailArgs(BaseModel):
    to: str
    subject: str
    body: str

    model_config = {"extra": "ignore"}


send_email_tool = Tool(
    name="send_email",
    description=(
        "Draft and propose an outbound email for human approval "
        "(Level 3 — calling this pauses for Approve/Reject in the UI before sending)."
    ),
    parameters=SendEmailArgs,
    risk_level=RiskLevel.LEVEL_3,
    func=mock_email_provider.send_email,
)

EMAIL_TOOLS: list[Tool] = [ingest_emails_tool, send_email_tool]


# --- Aggregated tools ---

ALL_TOOLS: list[Tool] = [
    *TODO_TOOLS,
    *EMAIL_TOOLS,
]
