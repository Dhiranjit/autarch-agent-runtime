"""Email triage feature workflow built on top of the core AgentRuntime."""

import json
from typing import TYPE_CHECKING, Any
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.models import AgentResponse, ExecutionMode
from app.db.models import Task
from app.quarantine.extractor import QuarantineExtractor

if TYPE_CHECKING:
    from app.runtime.agent import AgentRuntime


async def email_triage_module(
    session: AsyncSession,
    task: Task,
    runtime: "AgentRuntime",
    quarantine_extractor: QuarantineExtractor | None = None,
) -> AgentResponse:
    """Static email triage module: quarantine-extract email and propose actions."""
    ctx = json.loads(task.context_json or "{}")
    raw_email = ctx.get("raw_email", ctx) if isinstance(ctx, dict) else {}

    quarantine = quarantine_extractor or QuarantineExtractor()
    sanitized = await quarantine.extract_email(raw_email, runtime.llm)

    task.context_json = json.dumps({
        "trigger_type": "email",
        "source_sender": sanitized.sender,
        "thread_id": sanitized.thread_id,
        "subject": sanitized.subject,
    })
    session.add(task)

    system_prompt = (
        "You are a personal admin assistant. "
        "Triage the email and propose actions without executing them."
    )
    user_prompt = (
        f"Sender: {sanitized.sender}\n"
        f"Subject: {sanitized.subject}\n"
        f"Body:\n{sanitized.clean_body}"
    )

    return await runtime.llm.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=AgentResponse,
    )


class EmailTriagePipeline:
    """Sanitizes inbound email and delegates triage execution to AgentRuntime."""

    def __init__(
        self,
        runtime: "AgentRuntime",
        quarantine_extractor: QuarantineExtractor | None = None,
    ) -> None:
        self.runtime = runtime
        self.quarantine = quarantine_extractor or QuarantineExtractor()
        self.runtime.register_static_module("email_triage", self._run_module)

    async def _run_module(
        self,
        session: AsyncSession,
        task: Task,
        runtime: "AgentRuntime",
    ) -> AgentResponse:
        return await email_triage_module(
            session=session,
            task=task,
            runtime=runtime,
            quarantine_extractor=self.quarantine,
        )

    async def run(
        self,
        session: AsyncSession,
        task: Task,
        raw_email: dict[str, Any],
    ) -> Task:
        """Configure the task as STATIC email_triage and execute via AgentRuntime."""
        task.execution_mode = ExecutionMode.STATIC
        task.static_module = "email_triage"
        task.context_json = json.dumps({"raw_email": raw_email})
        session.add(task)
        return await self.runtime.run_task(session=session, task=task)
