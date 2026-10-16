"""FastAPI routes for email ingestion, approval resolution, audit logs, and SSE events."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.approval.manager import default_approval_manager
from app.config import settings
from app.core.models import ApprovalResolution, ApprovalStatus, TaskStatus
from app.db.database import get_session
from app.db.models import Approval, AuditLog, Task
from app.events.bus import default_event_bus
from app.runtime.llm import MockLLMProvider, OpenAILLMProvider
from app.runtime.pipeline import EmailTriagePipeline

router = APIRouter(prefix="/api")


class IngestEmailRequest(BaseModel):
    sender: str
    recipient: str = ""
    subject: str
    body: str
    thread_id: str | None = None


class ResolveApprovalRequest(BaseModel):
    action: ApprovalResolution
    edited_args: dict[str, Any] | None = None
    resolved_by: str = "user"


def get_triage_pipeline() -> EmailTriagePipeline:
    """Provide configured triage pipeline runtime."""
    if settings.openai_api_key:
        llm = OpenAILLMProvider()
    else:
        llm = MockLLMProvider()
    return EmailTriagePipeline(llm_provider=llm)


@router.post("/tasks/ingest-email")
async def ingest_email(
    request: IngestEmailRequest,
    session: AsyncSession = Depends(get_session),
    pipeline: EmailTriagePipeline = Depends(get_triage_pipeline),
):
    """Ingest an external email and run the triage control loop."""
    task = Task(source_type="email", status=TaskStatus.PENDING)
    session.add(task)
    await session.commit()
    await session.refresh(task)

    payload = request.model_dump()
    result_task = await pipeline.run(session=session, task=task, raw_email=payload)

    return {
        "task_id": result_task.id,
        "status": result_task.status,
    }


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    request: ResolveApprovalRequest,
    session: AsyncSession = Depends(get_session),
):
    """Approve, edit, or reject a pending approval."""
    try:
        approval = await default_approval_manager.resolve_approval(
            session=session,
            approval_id=approval_id,
            action=request.action,
            edited_args=request.edited_args,
            resolved_by=request.resolved_by,
        )
        return {
            "approval_id": approval.id,
            "status": approval.status,
            "task_id": approval.task_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks")
async def list_tasks(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, le=100),
):
    """List recent tasks."""
    statement = select(Task).order_by(desc(Task.created_at)).limit(limit)
    res = await session.exec(statement)
    return res.all()


@router.get("/approvals")
async def list_approvals(
    status: ApprovalStatus | None = None,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, le=100),
):
    """List approvals with optional status filter."""
    statement = select(Approval).order_by(desc(Approval.created_at)).limit(limit)
    if status:
        statement = statement.where(Approval.status == status)
    res = await session.exec(statement)
    return res.all()


@router.get("/audit")
async def list_audit_logs(
    task_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, le=200),
):
    """List append-only audit log entries."""
    statement = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
    if task_id:
        statement = statement.where(AuditLog.task_id == task_id)
    res = await session.exec(statement)
    return res.all()


@router.get("/events")
async def events_stream():
    """SSE endpoint for live real-time state transitions."""
    return EventSourceResponse(default_event_bus.subscribe())
