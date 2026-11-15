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
        tools: Sequence[Tool] | None = None,
    ) -> Approval:
        active_tools = list(tools) if tools is not None else self.tools
        args_payload = dict(tool_call.args)
        if tool_call.reasoning:
            args_payload["_reasoning"] = tool_call.reasoning

        approval = Approval(
            task_id=task_id,
            tool_call_id=tool_call.id,
            tool_name=tool_call.tool_name,
            proposed_args_json=json.dumps(args_payload),
            status=ApprovalStatus.PENDING,
        )
        session.add(approval)
        await session.flush()

        tool = get_tool(active_tools, tool_call.tool_name)
        risk_level = int(tool.risk_level) if tool else None

        audit = AuditLog(
            task_id=task_id,
            approval_id=approval.id,
            event_type="approval_requested",
            tool_name=tool_call.tool_name,
            risk_level=risk_level,
            policy_decision=PolicyAction.REQUIRE_APPROVAL,
            actor="system",
            payload_json=json.dumps({
                "tool_call_id": tool_call.id,
                "reasoning": tool_call.reasoning,
                "args": tool_call.args,
            }),
        )
        session.add(audit)
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
        res = await session.exec(stmt)
        return res.first() is not None

    async def resolve_approval(
        self,
        session: AsyncSession,
        approval_id: str,
        action: UserApprovalAction,
        resolved_by: str = "user",
        tools: Sequence[Tool] | None = None,
    ) -> Approval:
        active_tools = list(tools) if tools is not None else self.tools
        statement = select(Approval).where(Approval.id == approval_id)
        result = await session.exec(statement)
        approval = result.one_or_none()
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found.")

        if approval.status != ApprovalStatus.PENDING:
            return approval

        task = await session.get(Task, approval.task_id)
        now = datetime.now(timezone.utc)
        args_to_run = safe_json_loads(approval.proposed_args_json)
        args_to_run.pop("_reasoning", None)

        tool_outcome: dict[str, Any] = {
            "tool_call_id": approval.tool_call_id,
            "tool_name": approval.tool_name,
            "args": args_to_run,
        }

        if action == UserApprovalAction.REJECT:
            approval.status = ApprovalStatus.REJECTED
            approval.resolved_by = resolved_by
            approval.resolved_at = now
            session.add(approval)
            tool_outcome.update({
                "success": False,
                "output": f"User rejected execution of tool '{approval.tool_name}'.",
                "status": "REJECTED",
            })

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
            actor = "user_approved"
            tool_result = await execute_tool(
                active_tools,
                approval.tool_name,
                args_to_run,
                tool_call_id=approval.tool_call_id,
            )
            tool_outcome.update({
                "success": tool_result.success,
                "output": tool_result.output,
                "status": "APPROVED",
            })

            approval.status = ApprovalStatus.APPROVED
            approval.resolved_by = resolved_by
            approval.resolved_at = now
            session.add(approval)

            audit = AuditLog(
                task_id=approval.task_id,
                approval_id=approval.id,
                event_type="tool_executed" if tool_result.success else "tool_failed",
                tool_name=approval.tool_name,
                actor=actor,
                payload_json=json.dumps({
                    "args": args_to_run,
                    "output": tool_result.output,
                }),
            )
            session.add(audit)

        # Append resolved tool output into checkpointed messages_json and step history
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
            steps = existing_result.get("steps")
            if isinstance(steps, list) and steps:
                last_step = steps[-1]
                if isinstance(last_step, dict):
                    tool_results = last_step.setdefault("tool_results", [])
                    if isinstance(tool_results, list):
                        tool_results.append(tool_outcome)
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
