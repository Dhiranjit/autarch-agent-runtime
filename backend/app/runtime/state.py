"""Task state persistence and JSON serialization helpers."""

from datetime import datetime, timezone
import json
from typing import Any
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.models import TaskStatus
from app.db.models import Task
from app.events.bus import default_event_bus


def safe_json_loads(raw: str | None) -> dict[str, Any]:
    """Parse a JSON string into a dict, wrapping non-dict or invalid payloads safely."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": raw}


def safe_json_loads_list(raw: str | None) -> list[dict[str, Any]]:
    """Parse a JSON string into a list of dicts safely."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        return []
    except json.JSONDecodeError:
        return []


async def transition_task(
    session: AsyncSession,
    task: Task,
    status: TaskStatus,
    result: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> Task:
    """Persist a task status transition (with optional result/messages checkpoint) and emit SSE."""
    task.status = status
    if result is not None:
        task.result_json = json.dumps(result)
    if messages is not None:
        task.messages_json = json.dumps(messages)
    task.updated_at = datetime.now(timezone.utc)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await default_event_bus.publish(
        "task_updated",
        {"task_id": task.id, "status": task.status.value},
    )
    return task
