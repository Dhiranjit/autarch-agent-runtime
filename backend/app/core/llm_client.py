"""LLM Client using OpenAI SDK with native tool calling and structured outputs."""

from typing import Any
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel


class LLMClient:
    """Thin AsyncOpenAI wrapper for chat completions and structured parsing."""

    def __init__(self, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletionMessage:
        """Send a chat completion request and return the assistant message."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        completion = await self.client.chat.completions.create(**kwargs)
        return completion.choices[0].message

    async def parse_structured[T: BaseModel](
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
    ) -> T:
        """Run a tool-free structured output call for sandboxed extraction nodes."""
        completion = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=response_model,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError(f"LLM failed to parse {response_model.__name__}")
        return parsed
