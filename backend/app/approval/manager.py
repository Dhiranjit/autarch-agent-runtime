"""Persistent Approval Manager implementing human-in-the-loop gating."""

from collections.abc import Sequence
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
from app.runtime.state import safe_json_loads, safe_json_loads_list
from app.tools.registry import Tool, execute_tool, get_tool


class ApprovalManager:
    """Manages persistent approval queues, resolutions, and side-effect gating."""

    def __init__(self, tools: Sequence[Tool] | None = None) -> None:
        self._tools: list[Tool] | None = list(tools) if tools is not None else None

    @property
    def tools(self) -> list[Tool]:
        if self._tools is not None:
            return self._tools
        from app.tools.tools import ALL_TOOLS
        return list(ALL_TOOLS)

    async def request_approval(
        self,
        session: AsyncSession,
        task_id: str,
        tool_call: ProposedToolCall,
    ) -> Approval:
        approval = Approval(
            task_id=task_id,
            tool_call_id=tool_call.id,
            tool_name=tool_call.tool_name,
            proposed_args_json=json.dumps(tool_call.args),
            status=ApprovalStatus.PENDING,
        )
        session.add(approval)
        await session.flush()

        tool = get_tool(self.tools, tool_call.tool_name)
        risk_level = int(tool.risk_level) if tool else None

        session.add(
            AuditLog(
                task_id=task_id,
                approval_id=approval.id,
                event_type="approval_requested",
                tool_name=tool_call.tool_name,
                risk_level=risk_level,
                policy_decision=PolicyAction.REQUIRE_APPROVAL,
                actor="system",
                payload_json=json.dumps({
                    "tool_call_id": tool_call.id,
                    "args": tool_call.args,
                }),
            )
        )
        await session.commit()
        await session.refresh(approval)

        await default_event_bus.publish(
            "approval_requested",
            {
                "approval_id": approval.id,
                "task_id": task_id,
                "tool_call_id": tool_call.id,
                "tool_name": approval.tool_name,
                "proposed_args": tool_call.args,
            },
        )
        return approval

    async def has_pending_approvals(
        self,
        session: AsyncSession,
        task_id: str,
    ) -> bool:
        """Check whether a task still has any unresolved PENDING approvals."""
        stmt = select(Approval.id).where(
            Approval.task_id == task_id,
            Approval.status == ApprovalStatus.PENDING,
        )
        return (await session.exec(stmt)).first() is not None

    async def resolve_approval(
        self,
        session: AsyncSession,
        approval_id: str,
        action: UserApprovalAction,
        resolved_by: str = "user",
    ) -> Approval:
        approval = await session.get(Approval, approval_id)
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found.")

        if approval.status != ApprovalStatus.PENDING:
            return approval

        now = datetime.now(timezone.utc)
        args_to_run = safe_json_loads(approval.proposed_args_json)
        tool_outcome: dict[str, Any] = {
            "tool_call_id": approval.tool_call_id,
            "tool_name": approval.tool_name,
            "args": args_to_run,
        }

        if action == UserApprovalAction.REJECT:
            approval.status = ApprovalStatus.REJECTED
            tool_outcome.update({
                "success": False,
                "output": f"User rejected execution of tool '{approval.tool_name}'.",
                "status": "REJECTED",
            })
            session.add(
                AuditLog(
                    task_id=approval.task_id,
                    approval_id=approval.id,
                    event_type="approval_resolved",
                    tool_name=approval.tool_name,
                    policy_decision="REJECTED",
                    actor="user_rejected",
                    payload_json=json.dumps({"action": UserApprovalAction.REJECT}),
                )
            )
        else:
            tool_result = await execute_tool(
                self.tools,
                approval.tool_name,
                args_to_run,
                tool_call_id=approval.tool_call_id,
            )
            approval.status = ApprovalStatus.APPROVED
            tool_outcome.update({
                "success": tool_result.success,
                "output": tool_result.output,
                "status": "APPROVED",
            })
            session.add(
                AuditLog(
                    task_id=approval.task_id,
                    approval_id=approval.id,
                    event_type="tool_executed" if tool_result.success else "tool_failed",
                    tool_name=approval.tool_name,
                    actor="user_approved",
                    payload_json=json.dumps({
                        "args": args_to_run,
                        "output": tool_result.output,
                    }),
                )
            )

        approval.resolved_by = resolved_by
        approval.resolved_at = now
        session.add(approval)

        task = await session.get(Task, approval.task_id)
        if task:
            messages = safe_json_loads_list(task.messages_json)
            if approval.tool_call_id:
                messages.append({
                    "role": "tool",
                    "tool_call_id": approval.tool_call_id,
                    "content": json.dumps({
                        "success": tool_outcome["success"],
                        "status": tool_outcome["status"],
                        "output": tool_outcome["output"],
                    }),
                })
                task.messages_json = json.dumps(messages)

            existing_result = safe_json_loads(task.result_json)
            steps = existing_result.get("steps", [])
            if steps:
                steps[-1].setdefault("tool_results", []).append(tool_outcome)
            existing_result.setdefault("tool_results", []).append(tool_outcome)
            task.result_json = json.dumps(existing_result)
            task.updated_at = now
            session.add(task)

        await session.commit()
        await session.refresh(approval)

        await default_event_bus.publish(
            "tool_result",
            {
                "task_id": approval.task_id,
                "tool_call_id": approval.tool_call_id,
                "tool_name": approval.tool_name,
                "success": tool_outcome["success"],
                "output": tool_outcome["output"],
                "status": tool_outcome["status"],
            },
        )
        await default_event_bus.publish(
            "approval_resolved",
            {
                "approval_id": approval.id,
                "task_id": approval.task_id,
                "tool_call_id": approval.tool_call_id,
                "tool_name": approval.tool_name,
                "status": approval.status.value,
            },
        )

        return approval


default_approval_manager = ApprovalManager()
