"""Email triage pipeline runtime coordinating quarantine, LLM, policy, and execution."""

from datetime import datetime, timezone
import json
from typing import Any
from sqlmodel.ext.asyncio.session import AsyncSession

from app.approval.manager import default_approval_manager
from app.core.models import (
    ExecutionContext,
    TaskStatus,
    TriageResult,
)
from app.core.protocols import LLMProvider
from app.db.models import AuditLog, Task
from app.events.bus import default_event_bus
from app.policy.engine import PolicyEngine
from app.quarantine.extractor import QuarantineExtractor
from app.tools.registry import default_gateway


class EmailTriagePipeline:
    """Bounded, step-by-step pipeline for inbound email triage."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        policy_engine: PolicyEngine | None = None,
        quarantine_extractor: QuarantineExtractor | None = None,
    ) -> None:
        self.llm = llm_provider
        self.policy_engine = policy_engine or PolicyEngine()
        self.quarantine = quarantine_extractor or QuarantineExtractor()

    async def run(
        self,
        session: AsyncSession,
        task: Task,
        raw_email: dict[str, Any],
    ) -> Task:
        # Step 1: Update task status to PROCESSING
        task.status = TaskStatus.PROCESSING
        task.updated_at = datetime.now(timezone.utc)
        session.add(task)
        await session.commit()
        await default_event_bus.publish(
            "task_updated", {"task_id": task.id, "status": task.status.value}
        )

        # Step 2: Quarantine Ingestion & Sanitization
        sanitized = await self.quarantine.extract_email(raw_email, self.llm)

        # Step 3: Provenance-Bound Context
        context = ExecutionContext(
            trigger_type="email",
            source_sender=sanitized.sender,
            thread_id=sanitized.thread_id,
            metadata={"subject": sanitized.subject},
        )
        task.context_json = json.dumps(context.model_dump())
        session.add(task)

        # Step 4: Triage & Action Proposal (LLM as proposer only)
        triage_prompt = (
            f"Sender: {sanitized.sender}\n"
            f"Subject: {sanitized.subject}\n"
            f"Body:\n{sanitized.clean_body}"
        )
        triage_result = await self.llm.generate_structured(
            system_prompt="You are a personal admin assistant. Triage the email and propose actions without executing them.",
            user_prompt=triage_prompt,
            response_model=TriageResult,
        )

        # Update context metadata with triage summary
        context.metadata["summary"] = triage_result.summary
        task.context_json = json.dumps(context.model_dump())
        session.add(task)

        has_pending_approval = False

        # Step 5: Policy Evaluation & Execution / Approval Gating
        for proposal in triage_result.proposals:
            decision = self.policy_engine.evaluate(proposal, context)

            if decision.allowed and not decision.requires_approval:
                # Level 0–2: Auto-execute via Tool Gateway
                tool_res = await default_gateway.execute(proposal.tool_name, proposal.args)
                audit = AuditLog(
                    task_id=task.id,
                    event_type="tool_executed",
                    tool_name=proposal.tool_name,
                    risk_level=int(proposal.risk_level),
                    policy_decision="ALLOW",
                    actor="policy_auto",
                    payload_json=json.dumps({
                        "args": proposal.args,
                        "output": tool_res.output,
                        "success": tool_res.success,
                    }),
                )
                session.add(audit)

            elif decision.requires_approval:
                # Level 3: Gated by Approval Manager
                has_pending_approval = True
                await default_approval_manager.request_approval(
                    session=session,
                    task_id=task.id,
                    proposal=proposal,
                )

        # Step 6: Finalize Task State
        now = datetime.now(timezone.utc)
        if has_pending_approval:
            task.status = TaskStatus.WAITING_APPROVAL
        else:
            task.status = TaskStatus.COMPLETED

        task.updated_at = now
        session.add(task)
        await session.commit()
        await session.refresh(task)

        await default_event_bus.publish(
            "task_updated", {"task_id": task.id, "status": task.status.value}
        )
        return task

