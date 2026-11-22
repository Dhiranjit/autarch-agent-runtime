"""FastAPI routes for Orchestrator task execution, approvals, tool listing, and SSE events."""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.approval.manager import default_approval_manager
from app.config import settings
from app.core.llm_client import LLMClient
from app.core.models import ApprovalStatus, TaskStatus, UserApprovalAction
from app.db.database import async_session_maker, get_session
from app.db.models import Approval, Task, Todo
from app.events.bus import default_event_bus
from app.runtime.agent import AgentRuntime
from app.tools.tools import ALL_TOOLS

router = APIRouter(prefix="/api")

_background_tasks: set[asyncio.Task[None]] = set()


class CreateTaskRequest(BaseModel):
    prompt: str


class ResolveApprovalRequest(BaseModel):
    action: UserApprovalAction
    resolved_by: str = "user"


class UpdateTodoRequest(BaseModel):
    completed: bool


def get_runtime() -> AgentRuntime:
    """Provide configured AgentRuntime."""
    llm = LLMClient(
        api_key=settings.open_router_api_key or "",
        model=settings.model or "",
    )
    return AgentRuntime(llm_client=llm)


async def _run_task_in_background(task_id: str, runtime: AgentRuntime) -> None:
    async with async_session_maker() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return
        await runtime.run_task(session=session, task=task)


async def _resume_task_in_background(task_id: str, runtime: AgentRuntime) -> None:
    async with async_session_maker() as session:
        await runtime.resume_after_approval(session=session, task_id=task_id)


@router.post("/tasks")
async def create_task(
    request: CreateTaskRequest,
    session: AsyncSession = Depends(get_session),
    runtime: AgentRuntime = Depends(get_runtime),
):
    """Create a task and start the Orchestrator loop in the background."""
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Task prompt must not be empty.")

    task = Task(
        source_type="user",
        status=TaskStatus.QUEUED,
        context_json=json.dumps({"prompt": prompt}),
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    bg_task = asyncio.create_task(_run_task_in_background(task.id, runtime))
    _background_tasks.add(bg_task)
    bg_task.add_done_callback(_background_tasks.discard)

    return {
        "task_id": task.id,
        "status": task.status,
    }


@router.get("/tasks")
async def list_tasks(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=30, le=100),
):
    """List recent tasks."""
    statement = select(Task).order_by(desc(Task.created_at)).limit(limit)
    res = await session.exec(statement)
    return res.all()


@router.get("/approvals")
async def list_approvals(
    session: AsyncSession = Depends(get_session),
    task_id: str | None = Query(default=None),
    status: ApprovalStatus | None = Query(default=None),
    limit: int = Query(default=30, le=100),
):
    """List recent tool approvals, optionally filtered by task_id or status."""
    statement = select(Approval).order_by(desc(Approval.created_at)).limit(limit)
    if task_id is not None:
        statement = statement.where(Approval.task_id == task_id)
    if status is not None:
        statement = statement.where(Approval.status == status)
    res = await session.exec(statement)
    return res.all()


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    request: ResolveApprovalRequest,
    session: AsyncSession = Depends(get_session),
    runtime: AgentRuntime = Depends(get_runtime),
):
    """Resolve a pending approval (APPROVE or REJECT) and resume the paused Orchestrator loop."""
    try:
        approval = await default_approval_manager.resolve_approval(
            session=session,
            approval_id=approval_id,
            action=request.action,
            resolved_by=request.resolved_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    bg_task = asyncio.create_task(_resume_task_in_background(approval.task_id, runtime))
    _background_tasks.add(bg_task)
    bg_task.add_done_callback(_background_tasks.discard)

    return {
        "approval_id": approval.id,
        "task_id": approval.task_id,
        "status": approval.status,
    }


@router.get("/tools")
async def list_tools():
    """List registered tools and workflows available to the Orchestrator."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "risk_level": int(tool.risk_level),
        }
        for tool in ALL_TOOLS
    ]


@router.get("/todos")
async def list_todos(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, le=200),
):
    """List permanent user todos ordered newest first."""
    statement = select(Todo).order_by(desc(Todo.created_at)).limit(limit)
    res = await session.exec(statement)
    return res.all()


@router.patch("/todos/{todo_id}")
async def update_todo(
    todo_id: str,
    request: UpdateTodoRequest,
    session: AsyncSession = Depends(get_session),
):
    """Mark a todo as completed or incomplete."""
    todo = await session.get(Todo, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found.")
    todo.completed = request.completed
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return todo


@router.delete("/todos/{todo_id}")
async def delete_todo(
    todo_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a todo item."""
    todo = await session.get(Todo, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found.")
    await session.delete(todo)
    await session.commit()
    return {"deleted": True, "id": todo_id}


@router.get("/events")
async def events_stream():
    """SSE endpoint for live real-time agent steps, workflow steps, approvals, and tool calls."""
    return EventSourceResponse(default_event_bus.subscribe())
