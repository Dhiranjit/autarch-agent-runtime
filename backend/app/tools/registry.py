"""Tool execution gateway and registry."""

from collections.abc import Callable
import inspect
from typing import Any
from pydantic import BaseModel, ValidationError

from app.core.models import RiskLevel, ToolResult
from app.tools.builtin import mock_email_provider, mock_task_provider


class CreateTaskArgs(BaseModel):
    title: str
    description: str = ""

    model_config = {"extra": "ignore"}


class SendEmailArgs(BaseModel):
    to: str
    subject: str
    body: str

    model_config = {"extra": "ignore"}


class ToolRegistration(BaseModel):
    name: str
    risk_level: RiskLevel
    args_schema: type[BaseModel]
    description: str = ""

    model_config = {"arbitrary_types_allowed": True}


class ToolGateway:
    """Gateway that securely dispatches tool executions with parameter validation."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolRegistration, Callable]] = {}

    def register(
        self,
        name: str,
        risk_level: RiskLevel,
        args_schema: type[BaseModel],
        func: Callable,
        description: str = "",
    ) -> None:
        registration = ToolRegistration(
            name=name,
            risk_level=risk_level,
            args_schema=args_schema,
            description=description,
        )
        self._tools[name] = (registration, func)

    def get_tool(self, name: str) -> ToolRegistration | None:
        entry = self._tools.get(name)
        return entry[0] if entry else None

    async def execute(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' not registered in Tool Gateway.",
            )

        registration, func = self._tools[tool_name]

        # Validate arguments using the tool's schema
        try:
            validated_args = registration.args_schema(**args)
        except ValidationError as e:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Invalid arguments for tool '{tool_name}': {e}",
            )

        # Execute callable
        try:
            kwargs = validated_args.model_dump()
            if inspect.iscoroutinefunction(func):
                output = await func(**kwargs)
            else:
                output = func(**kwargs)

            return ToolResult(tool_name=tool_name, success=True, output=output)
        except Exception as exc:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Error executing tool '{tool_name}': {str(exc)}",
            )


# Default configured ToolGateway instance for Milestone 1
default_gateway = ToolGateway()
default_gateway.register(
    name="create_task",
    risk_level=RiskLevel.LEVEL_2,
    args_schema=CreateTaskArgs,
    func=mock_task_provider.create_task,
    description="Create an internal task item (Level 2).",
)
default_gateway.register(
    name="send_email",
    risk_level=RiskLevel.LEVEL_3,
    args_schema=SendEmailArgs,
    func=mock_email_provider.send_email,
    description="Send an outbound email (Level 3).",
)

