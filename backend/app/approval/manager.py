"""Persistent Approval Manager implementing human-in-the-loop gating."""

from datetime import datetime, timezone
import json
from typing import Any
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.models import (
    ActionProposal,
    ApprovalResolution,
    ApprovalStatus,
    TaskStatus,
)
from app.db.models import Approval, AuditLog, Task
from app.events.bus import default_event_bus
from app.tools.registry import default_gateway


class ApprovalManager:
    """Manages persistent approval queues, resolutions, and side-effect gating."""

    async def request_approval(
        self,
        session: AsyncSession,
        task_id: str,
        proposal: ActionProposal,
    ) -> Approval:
        args_payload = dict(proposal.args)
        if proposal.reasoning:
            args_payload["_reasoning"] = proposal.reasoning

        approval = Approval(
            task_id=task_id,
            tool_name=proposal.tool_name,
            proposed_args_json=json.dumps(args_payload),
            status=ApprovalStatus.PENDING,
        )
        session.add(approval)
        await session.flush()

        # Record in audit log
        audit = AuditLog(
            task_id=task_id,
            approval_id=approval.id,
            event_type="approval_requested",
            tool_name=proposal.tool_name,
            risk_level=int(proposal.risk_level),
            policy_decision="REQUIRE_APPROVAL",
            actor="system",
            payload_json=json.dumps({
                "reasoning": proposal.reasoning,
                "args": proposal.args,
            }),
        )
        session.add(audit)
        await session.commit()
        await session.refresh(approval)

        # Notify via SSE
        await default_event_bus.publish(
            "approval_requested",
            {
                "approval_id": approval.id,
                "task_id": task_id,
                "tool_name": approval.tool_name,
                "proposed_args": proposal.args,
            },
        )
        return approval

    async def resolve_approval(
        self,
        session: AsyncSession,
        approval_id: str,
        action: ApprovalResolution,
        edited_args: dict[str, Any] | None = None,
        resolved_by: str = "user",
    ) -> Approval:
        statement = select(Approval).where(Approval.id == approval_id)
        result = await session.exec(statement)
        approval = result.one_or_none()
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found.")

        # Idempotency check: if already resolved, return as-is
        if approval.status != ApprovalStatus.PENDING:
            return approval

        task_stmt = select(Task).where(Task.id == approval.task_id)
        task_result = await session.exec(task_stmt)
        task = task_result.one_or_none()

        now = datetime.now(timezone.utc)

        if action == ApprovalResolution.REJECT:
            approval.status = ApprovalStatus.REJECTED
            approval.resolved_by = resolved_by
            approval.resolved_at = now
            session.add(approval)

            audit = AuditLog(
                task_id=approval.task_id,
                approval_id=approval.id,
                event_type="approval_resolved",
                tool_name=approval.tool_name,
                policy_decision="REJECTED",
                actor="user_rejected",
                payload_json=json.dumps({"action": "REJECT"}),
            )
            session.add(audit)

        elif action in (ApprovalResolution.APPROVE, ApprovalResolution.EDIT):
            approval.status = ApprovalStatus.EXECUTING
            session.add(approval)
            await session.flush()

            if action == ApprovalResolution.EDIT:
                if edited_args is None:
                    raise ValueError("edited_args must be provided for EDIT resolution")
                args_to_run = edited_args
                approval.edited_args_json = json.dumps(edited_args)
                actor = "user_edited"
            else:
                args_to_run = json.loads(approval.proposed_args_json)
                actor = "user_approved"

            # Execute tool through ToolGateway
            tool_result = await default_gateway.execute(approval.tool_name, args_to_run)

            if tool_result.success:
                approval.status = ApprovalStatus.APPROVED
                approval.resolved_by = resolved_by
                approval.resolved_at = now
                session.add(approval)

                audit = AuditLog(
                    task_id=approval.task_id,
                    approval_id=approval.id,
                    event_type="tool_executed",
                    tool_name=approval.tool_name,
                    actor=actor,
                    payload_json=json.dumps({
                        "args": args_to_run,
                        "output": tool_result.output,
                    }),
                )
                session.add(audit)
            else:
                approval.status = ApprovalStatus.FAILED
                approval.resolved_by = resolved_by
                approval.resolved_at = now
                session.add(approval)

                audit = AuditLog(
                    task_id=approval.task_id,
                    approval_id=approval.id,
                    event_type="tool_failed",
                    tool_name=approval.tool_name,
                    actor=actor,
                    payload_json=json.dumps({"error": tool_result.error}),
                )
                session.add(audit)

        # Check if parent task has remaining pending approvals
        if task:
            pending_query = select(Approval).where(
                Approval.task_id == task.id,
                Approval.status == ApprovalStatus.PENDING,
            )
            pending_res = await session.exec(pending_query)
            remaining_pending = pending_res.all()

            if not remaining_pending:
                # All approvals are resolved
                if approval.status == ApprovalStatus.FAILED:
                    task.status = TaskStatus.FAILED
                else:
                    task.status = TaskStatus.COMPLETED
                task.updated_at = now
                session.add(task)

                await default_event_bus.publish(
                    "task_updated",
                    {"task_id": task.id, "status": task.status.value},
                )

        await session.commit()
        await session.refresh(approval)

        await default_event_bus.publish(
            "approval_resolved",
            {
                "approval_id": approval.id,
                "task_id": approval.task_id,
                "status": approval.status.value,
            },
        )

        return approval


# Default ApprovalManager instance
default_approval_manager = ApprovalManager()

