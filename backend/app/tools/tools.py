"""Tool definitions grouped by domain and predefined workflows."""

from pydantic import BaseModel

from app.core.models import RiskLevel
from app.features.email_triage import build_ingest_emails_tool
from app.runtime.context import MemoryScope, default_memory_store
from app.runtime.subagent import build_spawn_subagent_tool
from app.tools.builtin import mock_email_provider, todo_provider
from app.tools.registry import Tool


# ---------------------------------------------------------------------------
# Todo Tools
# ---------------------------------------------------------------------------

class CreateTodoArgs(BaseModel):
    title: str
    description: str = ""

    model_config = {"extra": "ignore"}


class ListTodosArgs(BaseModel):
    include_completed: bool = False

    model_config = {"extra": "ignore"}


todo_create_tool = Tool(
    name="todo_create",
    description=(
        "Save a permanent user to-do / reminder item in the Todo list. "
        "Only use for legitimate, actionable user tasks—never for spam, promotional, or suspicious content."
    ),
    parameters=CreateTodoArgs,
    risk_level=RiskLevel.LEVEL_2,
    func=todo_provider.create_todo,
)

todo_list_tool = Tool(
    name="todo_list",
    description="Read saved items from the permanent Todo list.",
    parameters=ListTodosArgs,
    risk_level=RiskLevel.LEVEL_0,
    func=todo_provider.list_todos,
)

TODO_TOOLS: list[Tool] = [todo_create_tool, todo_list_tool]


# ---------------------------------------------------------------------------
# Email Tools & Predefined Workflows
# ---------------------------------------------------------------------------

workflow_ingest_emails_tool = build_ingest_emails_tool()


class SendEmailArgs(BaseModel):
    to: str
    subject: str
    body: str

    model_config = {"extra": "ignore"}


email_send_tool = Tool(
    name="email_send",
    description=(
        "Draft and propose an outbound email with complete to, subject, and body fields "
        "once the recipient and message intent are known."
    ),
    parameters=SendEmailArgs,
    risk_level=RiskLevel.LEVEL_3,
    func=mock_email_provider.send_email,
)

EMAIL_TOOLS: list[Tool] = [workflow_ingest_emails_tool, email_send_tool]


# ---------------------------------------------------------------------------
# Memory Tools
# ---------------------------------------------------------------------------

class WriteMemoryArgs(BaseModel):
    scope: MemoryScope
    content: str

    model_config = {"extra": "ignore"}


memory_write_tool = Tool(
    name="memory_write",
    description=(
        "Replace the full contents of a markdown memory file. "
        "Use scope='persistent' for durable user facts, preferences, contacts, and standing rules (persistent.md). "
        "Use scope='working' for temporary short-term notes and ongoing context that aren't todos (working.md)."
    ),
    parameters=WriteMemoryArgs,
    risk_level=RiskLevel.LEVEL_2,
    func=default_memory_store.write,
)

MEMORY_TOOLS: list[Tool] = [memory_write_tool]


# ---------------------------------------------------------------------------
# Domains & Subagent Spawning
# ---------------------------------------------------------------------------

TOOL_DOMAINS: dict[str, list[Tool]] = {
    "todo": TODO_TOOLS,
    "email": EMAIL_TOOLS,
}

spawn_subagent_tool = build_spawn_subagent_tool(domains=TOOL_DOMAINS)


# ---------------------------------------------------------------------------
# Aggregated Tools
# ---------------------------------------------------------------------------

ALL_TOOLS: list[Tool] = [
    *TODO_TOOLS,
    *EMAIL_TOOLS,
    *MEMORY_TOOLS,
    spawn_subagent_tool,
]