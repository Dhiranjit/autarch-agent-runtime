"""Tool model, OpenAI schema conversion, and execution helpers."""

import inspect
from typing import Any
from pydantic import BaseModel, ValidationError
from collections.abc import Callable, Sequence
from app.core.models import RiskLevel, ToolResult


class Tool(BaseModel):
    """Tool definition matching OpenAI's tool format + app metadata."""
    name: str
    description: str
    parameters: type[BaseModel]
    risk_level: RiskLevel
    func: Callable[..., Any]

    model_config = {"arbitrary_types_allowed": True}

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert this tool into OpenAI's native function tool payload."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters.model_json_schema(),
            },
        }

    async def execute(self, args: dict[str, Any], tool_call_id: str = "") -> ToolResult:
        """Validate arguments with the Pydantic schema and execute the tool callable."""
        try:
            validated = self.parameters(**args)
        except ValidationError as exc:
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                success=False,
                output=f"Invalid arguments for tool '{self.name}': {exc}",
            )

        try:
            kwargs = validated.model_dump()
            if inspect.iscoroutinefunction(self.func):
                output = await self.func(**kwargs)
            else:
                output = self.func(**kwargs)
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                success=True,
                output=output,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                success=False,
                output=f"Error executing tool '{self.name}': {exc}",
            )


def get_tool(tools: Sequence[Tool], name: str) -> Tool | None:
    """Look up a tool by name from a collection of tools."""
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def to_openai_tools(tools: Sequence[Tool]) -> list[dict[str, Any]]:
    """Convert a collection of tools into OpenAI's native tools payload."""
    return [tool.to_openai_tool() for tool in tools]


async def execute_tool(
    tools: Sequence[Tool],
    tool_name: str,
    args: dict[str, Any],
    tool_call_id: str = "",
) -> ToolResult:
    """Look up and execute a tool by name from a collection of tools."""
    tool = get_tool(tools, tool_name)
    if tool is None:
        return ToolResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            success=False,
            output=f"Tool '{tool_name}' not found.",
        )
    return await tool.execute(args=args, tool_call_id=tool_call_id)
