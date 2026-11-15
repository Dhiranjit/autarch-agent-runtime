"""Isolated Subagent runner with scoped tools and ephemeral working memory."""

from collections.abc import Sequence
import json
from typing import Any
from pydantic import BaseModel, Field

from app.core.llm import LLMClient
from app.core.models import AgentProfile, PolicyAction, ProposedToolCall, RiskLevel
from app.events.bus import default_event_bus
from app.policy.engine import PolicyEngine
from app.tools.registry import Tool, execute_tool, to_openai_tools


class SubagentArgs(BaseModel):
    instruction: str = Field(
        description="Clear task instruction for the subagent to execute."
    )
    context: str = Field(
        default="",
        description="Optional supporting context or data for the subagent.",
    )

    model_config = {"extra": "ignore"}


class SubagentRunner:
    """Runs a specialized subagent in an isolated context window with scoped tools."""

    def __init__(
        self,
        profile: AgentProfile,
        llm_client: LLMClient,
        tools: Sequence[Tool] | None = None,
    ) -> None:
        self.profile = profile
        self.llm = llm_client
        self.tools: list[Tool] = list(tools) if tools is not None else []
        self.policy_engine = PolicyEngine(tools=self.tools)

    async def run(
        self,
        instruction: str,
        context: str = "",
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute an isolated while-tool-calls loop and return only the final summary."""
        openai_tools = to_openai_tools(self.tools) or None
        user_content = (
            f"Instruction: {instruction}\nContext:\n{context}"
            if context
            else instruction
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.profile.system_prompt},
            {"role": "user", "content": user_content},
        ]
        steps_taken = 0

        for step in range(1, self.profile.max_steps + 1):
            steps_taken = step
            await default_event_bus.publish(
                "subagent_step",
                {
                    "task_id": task_id,
                    "subagent": self.profile.name,
                    "step": step,
                    "phase": "thinking",
                },
            )

            assistant_msg = await self.llm.chat(messages=messages, tools=openai_tools)
            tool_calls = [
                tc for tc in (assistant_msg.tool_calls or []) if tc.type == "function"
            ]
            content = assistant_msg.content or ""

            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_msg.content,
            }
            if tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_entry)

            if not tool_calls:
                return {
                    "subagent": self.profile.name,
                    "status": "completed",
                    "output": content,
                    "steps_taken": steps_taken,
                }

            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    parsed_args = json.loads(tc.function.arguments or "{}")
                    if not isinstance(parsed_args, dict):
                        raise ValueError("Tool arguments must be a JSON object.")
                except (json.JSONDecodeError, ValueError) as exc:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({
                            "success": False,
                            "output": f"Invalid JSON arguments: {exc}",
                        }),
                    })
                    continue

                decision = self.policy_engine.evaluate(
                    ProposedToolCall(id=tc.id, tool_name=tool_name, args=parsed_args)
                )
                if decision.action != PolicyAction.ALLOW:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({
                            "success": False,
                            "output": (
                                f"Subagent '{self.profile.name}' is not permitted to execute "
                                f"'{tool_name}' ({decision.action.value}: {decision.reason})."
                            ),
                        }),
                    })
                    continue

                tool_res = await execute_tool(
                    self.tools,
                    tool_name=tool_name,
                    args=parsed_args,
                    tool_call_id=tc.id,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({
                        "success": tool_res.success,
                        "output": tool_res.output,
                    }),
                })

        return {
            "subagent": self.profile.name,
            "status": "max_steps_exceeded",
            "output": f"Subagent '{self.profile.name}' exceeded max_steps ({self.profile.max_steps}).",
            "steps_taken": steps_taken,
        }

    def as_tool(self, risk_level: RiskLevel = RiskLevel.LEVEL_0) -> Tool:
        """Expose this SubagentRunner as a callable Tool for the Orchestrator."""

        async def _invoke_subagent(instruction: str, context: str = "") -> dict[str, Any]:
            return await self.run(instruction=instruction, context=context)

        return Tool(
            name=f"delegate_{self.profile.name}",
            description=self.profile.description,
            parameters=SubagentArgs,
            risk_level=risk_level,
            func=_invoke_subagent,
        )
