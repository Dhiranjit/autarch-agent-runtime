"""LLM provider implementations: MockLLMProvider and OpenAILLMProvider."""

from typing import Any, TypeVar
from pydantic import BaseModel

from app.config import settings
from app.core.models import ActionProposal, RiskLevel, SanitizedEmail, TriageResult
from app.core.protocols import LLMProvider

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider:
    """Deterministic LLM provider for tests and offline execution."""

    def __init__(self, predefined_responses: dict[type[BaseModel], BaseModel] | None = None) -> None:
        self.predefined_responses: dict[type[BaseModel], BaseModel] = predefined_responses or {}

    def set_response(self, model_type: type[BaseModel], response: BaseModel) -> None:
        self.predefined_responses[model_type] = response

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        if response_model in self.predefined_responses:
            return self.predefined_responses[response_model]  # type: ignore

        # Deterministic default fallbacks for known schemas
        if response_model == SanitizedEmail:
            # Parse basic lines from user_prompt
            sender = "alice@example.com"
            subject = "Follow up on project"
            body = "Please schedule a sync and send a confirmation email."
            for line in user_prompt.splitlines():
                if line.startswith("Sender:"):
                    sender = line.split(":", 1)[1].strip() or sender
                elif line.startswith("Subject:"):
                    subject = line.split(":", 1)[1].strip() or subject
                elif line.startswith("Cleaned Body:"):
                    body = user_prompt.split("Cleaned Body:\n", 1)[-1].strip() or body

            return SanitizedEmail(  # type: ignore
                sender=sender,
                subject=subject,
                clean_body=body,
            )

        if response_model == TriageResult:
            # Standard vertical slice triage proposal:
            # 1. create_task (Level 2 - internal mutation)
            # 2. send_email (Level 3 - external side effect, matches sender provenance)
            sender = "alice@example.com"
            for line in user_prompt.splitlines():
                if line.startswith("Sender:"):
                    sender = line.split(":", 1)[1].strip() or sender

            return TriageResult(  # type: ignore
                summary="Meeting request identified. Proposing task creation and confirmation reply.",
                proposals=[
                    ActionProposal(
                        tool_name="create_task",
                        args={"title": "Prepare meeting agenda", "description": "Prep agenda based on email"},
                        risk_level=RiskLevel.LEVEL_2,
                        reasoning="Track agenda preparation task internally.",
                    ),
                    ActionProposal(
                        tool_name="send_email",
                        args={
                            "to": sender,
                            "subject": "Re: Follow up on project",
                            "body": "Sounds good! I have scheduled the sync.",
                        },
                        risk_level=RiskLevel.LEVEL_3,
                        reasoning="Send meeting confirmation to original sender.",
                    ),
                ],
            )

        raise ValueError(f"No mock response configured for model {response_model}")


class OpenAILLMProvider:
    """OpenAI SDK structured output provider."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self.model = model or settings.openai_model

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        completion = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(f"OpenAI failed to parse response into {response_model.__name__}")
        return parsed

