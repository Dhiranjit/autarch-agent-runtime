"""Policy-gated tool execution and audit logging for the Orchestrator loop."""

import json
from typing import Any
from sqlmodel.ext.asyncio.session import AsyncSession

from app.approval.manager import ApprovalManager, default_approval_manager
from app.core.models import PolicyAction, ProposedToolCall
from app.db.models import AuditLog, Task
from app.policy.engine import PolicyEngine
from app.tools.registry import execute_tool, get_tool


def _log_tool_audit(
    session: AsyncSession,
    task_id: str,
    event_type: str,
    tool_name: str,
    risk_level: int | None,
    policy_decision: PolicyAction,
    payload: dict[str, Any],
) -> None:
    session.add(
        AuditLog(
            task_id=task_id,
            event_type=event_type,
            tool_name=tool_name,
            risk_level=risk_level,
            policy_decision=policy_decision,
            actor="policy_auto",
            payload_json=json.dumps(payload),
        )
    )


async def evaluate_and_run_tool_call(
    session: AsyncSession,
    task: Task,
    tool_call: ProposedToolCall,
    policy_engine: PolicyEngine,
    approval_manager: ApprovalManager = default_approval_manager,
) -> dict[str, Any]:
    """Evaluate a single tool call against PolicyEngine; execute, deny, or request approval."""
    tools = policy_engine.tools
    decision = policy_engine.evaluate(tool_call)
    tool = get_tool(tools, tool_call.tool_name)
    risk_level = int(tool.risk_level) if tool else None

    if decision.action == PolicyAction.ALLOW:
        tool_res = await execute_tool(
            tools,
            tool_call.tool_name,
            tool_call.args,
            tool_call_id=tool_call.id,
        )
        _log_tool_audit(
            session=session,
            task_id=task.id,
            event_type="tool_executed" if tool_res.success else "tool_failed",
            tool_name=tool_call.tool_name,
            risk_level=risk_level,
            policy_decision=PolicyAction.ALLOW,
            payload={
                "tool_call_id": tool_call.id,
                "args": tool_call.args,
                "output": tool_res.output,
                "success": tool_res.success,
            },
        )
        await session.commit()
        return {
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.tool_name,
            "args": tool_call.args,
            "success": tool_res.success,
            "output": tool_res.output,
            "status": "ALLOW",
        }

    if decision.action == PolicyAction.REQUIRE_APPROVAL:
        approval = await approval_manager.request_approval(
            session=session,
            task_id=task.id,
            tool_call=tool_call,
        )
        return {
            "tool_call_id": tool_call.id,
            "approval_id": approval.id,
            "tool_name": tool_call.tool_name,
            "args": tool_call.args,
            "success": False,
            "output": f"Waiting for user approval (approval_id={approval.id}).",
            "status": "REQUIRE_APPROVAL",
        }

    _log_tool_audit(
        session=session,
        task_id=task.id,
        event_type="tool_denied",
        tool_name=tool_call.tool_name,
        risk_level=risk_level,
        policy_decision=PolicyAction.DENY,
        payload={
            "tool_call_id": tool_call.id,
            "args": tool_call.args,
            "reason": decision.reason,
        },
    )
    await session.commit()
    return {
        "tool_call_id": tool_call.id,
        "tool_name": tool_call.tool_name,
        "args": tool_call.args,
        "success": False,
        "output": decision.reason,
        "status": "DENY",
        "reason": decision.reason,
    }
