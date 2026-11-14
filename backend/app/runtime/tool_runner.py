"""Policy-gated tool execution and audit logging for AgentRuntime."""

import json
from typing import Any
from sqlmodel.ext.asyncio.session import AsyncSession

from app.approval.manager import ApprovalManager, default_approval_manager
from app.core.models import PolicyAction, ProposedToolCall
from app.db.models import AuditLog, Task
from app.policy.engine import PolicyEngine
from app.tools.registry import default_gateway


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


async def process_tool_calls(
    session: AsyncSession,
    task: Task,
    tool_calls: list[ProposedToolCall],
    policy_engine: PolicyEngine,
    approval_manager: ApprovalManager = default_approval_manager,
) -> tuple[list[dict[str, Any]], bool]:
    """Evaluate proposed tool calls against policy, executing allowed tools or queuing approvals."""
    tool_results: list[dict[str, Any]] = []
    has_pending_approval = False

    for tool_call in tool_calls:
        decision = policy_engine.evaluate(tool_call)
        tool_reg = default_gateway.get_tool(tool_call.tool_name)
        risk_level = int(tool_reg.risk_level) if tool_reg else None

        if decision.action == PolicyAction.ALLOW:
            tool_res = await default_gateway.execute(
                tool_call.tool_name,
                tool_call.args,
                tool_call_id=tool_call.id,
            )
            _log_tool_audit(
                session=session,
                task_id=task.id,
                event_type="tool_executed",
                tool_name=tool_call.tool_name,
                risk_level=risk_level,
                policy_decision=PolicyAction.ALLOW,
                payload={
                    "args": tool_call.args,
                    "output": tool_res.output,
                    "success": tool_res.success,
                },
            )
            tool_results.append({
                "tool_name": tool_call.tool_name,
                "success": tool_res.success,
                "output": tool_res.output,
                "status": "ALLOW",
            })

        elif decision.action == PolicyAction.REQUIRE_APPROVAL:
            has_pending_approval = True
            await approval_manager.request_approval(
                session=session,
                task_id=task.id,
                tool_call=tool_call,
            )
            tool_results.append({
                "tool_name": tool_call.tool_name,
                "status": "REQUIRE_APPROVAL",
            })

        elif decision.action == PolicyAction.DENY:
            _log_tool_audit(
                session=session,
                task_id=task.id,
                event_type="tool_denied",
                tool_name=tool_call.tool_name,
                risk_level=risk_level,
                policy_decision=PolicyAction.DENY,
                payload={
                    "args": tool_call.args,
                    "reason": decision.reason,
                },
            )
            tool_results.append({
                "tool_name": tool_call.tool_name,
                "success": False,
                "status": "DENY",
                "reason": decision.reason,
            })

    return tool_results, has_pending_approval
