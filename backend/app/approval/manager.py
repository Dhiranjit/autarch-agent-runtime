"""Persistent Approval Manager implementing human-in-the-loop gating."""

from datetime import datetime, timezone
import json
from typing import Any
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.models import (
    ApprovalStatus,
    PolicyAction,
    ProposedToolCall,
    UserApprovalAction,
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
        tool_call: ProposedToolCall,
    ) -> Approval:
        args_payload = dict(tool_call.args)
        if tool_call.reasoning:
            args_payload["_reasoning"] = tool_call.reasoning

        approval = Approval(
            task_id=task_id,
            tool_name=tool_call.tool_name,
            proposed_args_json=json.dumps(args_payload),
            status=ApprovalStatus.PENDING,
        )
        session.add(approval)
        await session.flush()

        tool_reg = default_gateway.get_tool(tool_call.tool_name)
        risk_level = int(tool_reg.risk_level) if tool_reg else None

        # Record in audit log
        audit = AuditLog(
            task_id=task_id,
            approval_id=approval.id,
            event_type="approval_requested",
            tool_name=tool_call.tool_name,
            risk_level=risk_level,
            policy_decision=PolicyAction.REQUIRE_APPROVAL,
            actor="system",
            payload_json=json.dumps({
                "reasoning": tool_call.reasoning,
                "args": tool_call.args,
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
                "proposed_args": tool_call.args,
            },
        )
        return approval

    async def resolve_approval(
        self,
        session: AsyncSession,
        approval_id: str,
        action: UserApprovalAction,
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
        tool_outcome: dict[str, Any] = {"tool_name": approval.tool_name}

        if action == UserApprovalAction.REJECT:
            approval.status = ApprovalStatus.REJECTED
            approval.resolved_by = resolved_by
            approval.resolved_at = now
            session.add(approval)
            tool_outcome.update({"success": False, "status": "REJECTED"})

            audit = AuditLog(
                task_id=approval.task_id,
                approval_id=approval.id,
                event_type="approval_resolved",
                tool_name=approval.tool_name,
                policy_decision="REJECTED",
                actor="user_rejected",
                payload_json=json.dumps({"action": UserApprovalAction.REJECT}),
            )
            session.add(audit)

        elif action == UserApprovalAction.APPROVE:
            args_to_run = json.loads(approval.proposed_args_json)
            args_to_run.pop("_reasoning", None)
            actor = "user_approved"

            # Execute tool through ToolGateway
            tool_result = await default_gateway.execute(approval.tool_name, args_to_run)
            tool_outcome.update({
                "success": tool_result.success,
                "output": tool_result.output,
                "status": "APPROVED",
            })

            approval.status = ApprovalStatus.APPROVED
            approval.resolved_by = resolved_by
            approval.resolved_at = now
            session.add(approval)

            if tool_result.success:
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
                audit = AuditLog(
                    task_id=approval.task_id,
                    approval_id=approval.id,
                    event_type="tool_failed",
                    tool_name=approval.tool_name,
                    actor=actor,
                    payload_json=json.dumps({"output": tool_result.output}),
                )
                session.add(audit)

        # Record resolved tool outcome on parent task; AgentRuntime handles task status transitions.
        if task:
            try:
                existing_result = json.loads(task.result_json or "{}")
                if not isinstance(existing_result, dict):
                    existing_result = {"raw_result": existing_result}
            except json.JSONDecodeError:
                existing_result = {}
            existing_result.setdefault("tool_results", []).append(tool_outcome)
            task.result_json = json.dumps(existing_result)
            task.updated_at = now
            session.add(task)

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

