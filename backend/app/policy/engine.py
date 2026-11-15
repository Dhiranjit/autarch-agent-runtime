"""Deterministic Policy Engine enforcing safety invariants."""

from collections.abc import Sequence

from app.core.models import PolicyAction, PolicyDecision, ProposedToolCall, RiskLevel
from app.tools.registry import Tool, get_tool
from app.tools.tools import ALL_TOOLS


class PolicyEngine:
    """Pure Python deterministic policy evaluator."""

    def __init__(self, tools: Sequence[Tool] | None = None) -> None:
        self.tools: list[Tool] = list(tools) if tools is not None else list(ALL_TOOLS)

    def evaluate(self, tool_call: ProposedToolCall) -> PolicyDecision:
        """Evaluate a proposed tool call against the tool risk matrix."""
        tool = get_tool(self.tools, tool_call.tool_name)
        if tool is None:
            return PolicyDecision(
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                action=PolicyAction.DENY,
                reason=f"Unregistered tool '{tool_call.tool_name}' denied by default.",
            )

        risk_level = tool.risk_level

        # Level 0, 1, 2: Internal reads, staging, and mutations are auto-approved
        if risk_level in (RiskLevel.LEVEL_0, RiskLevel.LEVEL_1, RiskLevel.LEVEL_2):
            return PolicyDecision(
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                action=PolicyAction.ALLOW,
                reason=f"Risk level {risk_level.name} is auto-approved.",
            )

        # Level 3, 4: External side-effects and payments require human approval
        if risk_level in (RiskLevel.LEVEL_3, RiskLevel.LEVEL_4):
            return PolicyDecision(
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                action=PolicyAction.REQUIRE_APPROVAL,
                reason=f"Risk level {risk_level.name} requires user approval.",
            )

        # Deny-by-default for unknown risk levels
        return PolicyDecision(
            tool_call_id=tool_call.id,
            tool_name=tool_call.tool_name,
            action=PolicyAction.DENY,
            reason="Unknown risk level denied by default.",
        )
