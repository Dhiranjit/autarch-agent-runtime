"""Task state persistence, child spawning, and step-order graph scheduling."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import json
from typing import Any
from sqlmodel import asc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.models import SubTask, TaskStatus
from app.db.models import Task
from app.events.bus import default_event_bus

_ACTIVE_STATUSES = (
    TaskStatus.EXECUTING,
    TaskStatus.WAITING_APPROVAL,
    TaskStatus.WAITING_CHILDREN,
)


def safe_json_loads(raw: str | None) -> dict[str, Any]:
    """Parse a JSON string into a dict, wrapping non-dict or invalid payloads safely."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": raw}


def parse_subtask_context(context: str) -> dict[str, Any]:
    """Parse SubTask context as JSON object or wrap plain text as instruction."""
    if not context:
        return {}
    try:
        parsed = json.loads(context)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"instruction": context}


async def transition_task(
    session: AsyncSession,
    task: Task,
    status: TaskStatus,
    result: dict[str, Any] | None = None,
) -> Task:
    """Persist a task status transition (and optional result) and emit task_updated."""
    task.status = status
    if result is not None:
        task.result_json = json.dumps(result)
    task.updated_at = datetime.now(timezone.utc)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await default_event_bus.publish(
        "task_updated",
        {"task_id": task.id, "status": task.status.value},
    )
    return task


async def get_task_depth(session: AsyncSession, task: Task, max_depth: int) -> int:
    """Compute depth of task from root by walking parent links up to max_depth."""
    depth = 0
    current_parent_id = task.parent_task_id
    while current_parent_id and depth <= max_depth:
        depth += 1
        parent = await session.get(Task, current_parent_id)
        current_parent_id = parent.parent_task_id if parent else None
    return depth


async def get_children(session: AsyncSession, parent_id: str) -> list[Task]:
    """Fetch direct child tasks ordered by step_order then created_at."""
    statement = (
        select(Task)
        .where(Task.parent_task_id == parent_id)
        .order_by(asc(Task.step_order), asc(Task.created_at))
    )
    res = await session.exec(statement)
    return list(res.all())


async def has_queued_children(session: AsyncSession, parent_id: str) -> bool:
    """Return whether parent_id still has any QUEUED child tasks."""
    statement = select(Task.id).where(
        Task.parent_task_id == parent_id,
        Task.status == TaskStatus.QUEUED,
    )
    res = await session.exec(statement)
    return res.first() is not None


def spawn_subtasks(session: AsyncSession, parent_task: Task, subtasks: list[SubTask]) -> None:
    """Stage QUEUED child Task rows for each SubTask under parent_task."""
    root_id = parent_task.root_task_id or parent_task.id
    for sub in subtasks:
        child = Task(
            parent_task_id=parent_task.id,
            root_task_id=root_id,
            step_order=sub.step_order,
            execution_mode=sub.execution_mode,
            static_module=sub.static_module,
            skill_name=sub.skill_name,
            source_type=parent_task.source_type,
            status=TaskStatus.QUEUED,
            context_json=json.dumps(parse_subtask_context(sub.context)),
        )
        session.add(child)


async def finalize_parent(
    session: AsyncSession,
    parent_task: Task,
    children: list[Task],
    failed: bool,
) -> Task:
    """Aggregate child results onto parent_task and transition it to COMPLETED or FAILED."""
    parent_result = safe_json_loads(parent_task.result_json)
    parent_result["children"] = [
        {
            "task_id": c.id,
            "step_order": c.step_order,
            "execution_mode": c.execution_mode.value,
            "static_module": c.static_module,
            "skill_name": c.skill_name,
            "status": c.status.value,
            "result": safe_json_loads(c.result_json),
        }
        for c in children
    ]
    final_status = TaskStatus.FAILED if failed else TaskStatus.COMPLETED
    return await transition_task(session, parent_task, final_status, result=parent_result)


async def run_next_step_group(
    session: AsyncSession,
    parent_task: Task,
    run_child: Callable[[str], Awaitable[None]],
) -> bool:
    """Execute ready step_order batches sequentially until blocked or finalized.

    Returns True if parent_task reached COMPLETED/FAILED, or False if waiting on active children.
    """
    parent_id = parent_task.id
    while True:
        children = await get_children(session, parent_id)
        if not children:
            return False

        if any(c.status in _ACTIVE_STATUSES for c in children):
            return False

        if any(c.status == TaskStatus.FAILED for c in children):
            await finalize_parent(session, parent_task, children, failed=True)
            return True

        queued = [c for c in children if c.status == TaskStatus.QUEUED]
        if not queued:
            await finalize_parent(session, parent_task, children, failed=False)
            return True

        next_step = min(c.step_order for c in queued)
        batch = [c for c in queued if c.step_order == next_step]

        prior_results = [
            {
                "task_id": c.id,
                "step_order": c.step_order,
                "static_module": c.static_module,
                "skill_name": c.skill_name,
                "result": safe_json_loads(c.result_json),
            }
            for c in children
            if c.status == TaskStatus.COMPLETED and c.step_order < next_step
        ]
        if prior_results:
            for child in batch:
                child_ctx = safe_json_loads(child.context_json)
                child_ctx["prior_results"] = prior_results
                child.context_json = json.dumps(child_ctx)
                session.add(child)

        await session.commit()
        await asyncio.gather(*(run_child(child.id) for child in batch))

        session.expire_all()
        refreshed_parent = await session.get(Task, parent_id)
        if refreshed_parent is None:
            return False
        parent_task = refreshed_parent
