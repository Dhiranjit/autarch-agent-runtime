"""Core protocols and interfaces."""

from typing import Any, Protocol, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Narrow structured LLM provider interface."""

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        """Generate structured output validated against a Pydantic model."""
        ...


class EmailProvider(Protocol):
    """External email provider interface."""

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        """Send an outbound email."""
        ...


class TaskProvider(Protocol):
    """External task tracking provider interface."""

    async def create_task(
        self,
        title: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create an internal or external task."""
        ...

