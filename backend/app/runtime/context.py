"""Markdown memory files and live SQLite context rendering for AgentRuntime."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.core.models import ApprovalStatus
from app.db.models import Approval, Task, Todo
from app.runtime.state import safe_json_loads

MemoryScope = Literal["persistent", "working"]

MEMORY_FILES: dict[MemoryScope, str] = {
    "persistent": "persistent.md",
    "working": "working.md",
}


class MemoryStore:
    """Plain markdown file store for persistent and working memory."""

    def __init__(self, memory_dir: Path | None = None) -> None:
        self.memory_dir = memory_dir or settings.memory_dir

    def _path(self, scope: MemoryScope) -> Path:
        return self.memory_dir / MEMORY_FILES[scope]

    def ensure_files(self) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        for scope in MEMORY_FILES:
            path = self._path(scope)
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def read(self, scope: MemoryScope) -> str:
        self.ensure_files()
        return self._path(scope).read_text(encoding="utf-8").strip()

    def write(self, scope: MemoryScope, content: str) -> dict[str, Any]:
        self.ensure_files()
        cleaned = content.strip()
        self._path(scope).write_text(f"{cleaned}\n" if cleaned else "", encoding="utf-8")
        return {"scope": scope, "status": "updated"}


def _truncate(text: str, limit: int = 160) -> str:
    single_line = " ".join(text.split())
    return single_line if len(single_line) <= limit else f"{single_line[:limit - 3]}..."


def _format_todos(todos: list[Todo]) -> str:
    if not todos:
        return "(none)"
    lines = []
    for todo in todos:
        desc_suffix = f": {todo.description}" if todo.description else ""
        lines.append(f"- [ ] {todo.title} (`{todo.id}`){desc_suffix}")
    return "\n".join(lines)


def _format_approvals(approvals: list[Approval]) -> str:
    if not approvals:
        return "(none)"
    return "\n".join(
        f"- `{a.tool_name}` (`{a.id}`, task `{a.task_id}`): {a.proposed_args_json}"
        for a in approvals
    )


def _format_tasks(tasks: list[Task]) -> str:
    if not tasks:
        return "(none)"
    lines = []
    for task in tasks:
        ctx = safe_json_loads(task.context_json)
        prompt = _truncate(str(ctx.get("prompt") or task.context_json))
        result = safe_json_loads(task.result_json)
        outcome = result.get("message") or result.get("error") or ""
        outcome_suffix = f" -> {_truncate(str(outcome))}" if outcome else ""
        lines.append(f'- [{task.status.value}] "{prompt}"{outcome_suffix}')
    return "\n".join(lines)


async def build_runtime_context(
    session: AsyncSession,
    current_task_id: str | None = None,
    memory_store: MemoryStore | None = None,
    recent_task_limit: int = 5,
) -> str:
    """Assemble persistent/working markdown files and live SQLite state into one markdown block."""
    store = memory_store or default_memory_store
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    persistent = store.read("persistent") or "(empty)"
    working = store.read("working") or "(empty)"

    todos_res = await session.exec(
        select(Todo)
        .where(Todo.completed == False)  # noqa: E712
        .order_by(desc(Todo.created_at))
    )
    approvals_res = await session.exec(
        select(Approval)
        .where(Approval.status == ApprovalStatus.PENDING)
        .order_by(desc(Approval.created_at))
    )
    tasks_stmt = select(Task).order_by(desc(Task.created_at)).limit(recent_task_limit)
    if current_task_id is not None:
        tasks_stmt = tasks_stmt.where(Task.id != current_task_id)
    tasks_res = await session.exec(tasks_stmt)

    return "\n".join([
        "# Runtime Context",
        "",
        "## Current Time",
        now,
        "",
        "## Persistent Memory (persistent.md)",
        persistent,
        "",
        "## Working Scratchpad (working.md)",
        working,
        "",
        "## Live State",
        "",
        "### Open Todos",
        _format_todos(list(todos_res.all())),
        "",
        "### Pending Approvals",
        _format_approvals(list(approvals_res.all())),
        "",
        "### Recent Tasks",
        _format_tasks(list(tasks_res.all())),
    ])


default_memory_store = MemoryStore()
