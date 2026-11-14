"""Core agent runtime orchestrating static modules, dynamic turns, tools, and task graphs."""

from collections.abc import Awaitable, Callable
import json
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm import LLMClient
from app.core.models import (
    AgentResponse,
    ApprovalStatus,
    ExecutionMode,
    TaskStatus,
)
from app.db.database import async_session_maker
from app.db.models import Approval, Task
from app.policy.engine import PolicyEngine
from app.runtime.task_graph import (
    get_task_depth,
    has_queued_children,
    run_next_step_group,
    safe_json_loads,
    spawn_subtasks,
    transition_task,
)
from app.runtime.tool_runner import process_tool_calls

StaticModuleHandler = Callable[[AsyncSession, Task, "AgentRuntime"], Awaitable[AgentResponse]]

_DYNAMIC_SYSTEM_PROMPT = (
    "You are a personal admin assistant orchestrator. "
    "Propose direct tool calls and/or structured subtasks without executing tools directly."
)


class AgentRuntime:
    """Core orchestrator for static modules, dynamic planning, policy gating, and child task graphs."""

    def __init__(
        self,
        llm_client: LLMClient,
        policy_engine: PolicyEngine | None = None,
        max_depth: int = 5,
        session_factory: async_sessionmaker[AsyncSession] = async_session_maker,
    ) -> None:
        self.llm = llm_client
        self.policy_engine = policy_engine or PolicyEngine()
        self.max_depth = max_depth
        self.session_factory = session_factory
        self._static_modules: dict[str, StaticModuleHandler] = {}

    def register_static_module(self, module_name: str, handler: StaticModuleHandler) -> None:
        """Register a predefined static execution module by name."""
        self._static_modules[module_name] = handler

    async def run_task(
        self,
        session: AsyncSession,
        task: Task,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> Task:
        """Execute a task according to its execution_mode (STATIC or DYNAMIC)."""
        factory = session_factory or self.session_factory
        if task.root_task_id is None:
            task.root_task_id = task.id
        await transition_task(session, task, TaskStatus.EXECUTING)

        try:
            agent_response = await self._execute_turn(session, task)
            return await self._apply_agent_response(
                session=session,
                task=task,
                agent_response=agent_response,
                factory=factory,
                allow_subtasks=(task.execution_mode == ExecutionMode.DYNAMIC),
            )
        except Exception as exc:
            return await transition_task(session, task, TaskStatus.FAILED, result={"error": str(exc)})

    async def resume_after_approval(
        self,
        session: AsyncSession,
        task_id: str,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> Task | None:
        """Transition a resumed task after approval resolution and advance parent steps if ready."""
        task = await session.get(Task, task_id)
        if not task:
            return None

        factory = session_factory or self.session_factory

        if task.status == TaskStatus.WAITING_APPROVAL:
            if await self._has_pending_approvals(session, task.id):
                return task

            if self._has_failed_approved_tool(task):
                await transition_task(session, task, TaskStatus.FAILED)
            elif await has_queued_children(session, task.id):
                await transition_task(session, task, TaskStatus.WAITING_CHILDREN)
                await self._run_step_group(session, task, factory)
            else:
                await transition_task(session, task, TaskStatus.COMPLETED)
        elif task.status == TaskStatus.WAITING_CHILDREN:
            await self._run_step_group(session, task, factory)

        await session.refresh(task)
        await self._advance_ancestors(session, task, factory)
        await session.refresh(task)
        return task

    async def _execute_turn(self, session: AsyncSession, task: Task) -> AgentResponse:
        if task.execution_mode == ExecutionMode.STATIC:
            if not task.static_module or task.static_module not in self._static_modules:
                raise ValueError(f"Unknown static module: {task.static_module!r}")
            handler = self._static_modules[task.static_module]
            return await handler(session, task, self)

        ctx = safe_json_loads(task.context_json)
        user_prompt = json.dumps(ctx, indent=2) if ctx else "{}"
        return await self.llm.generate_structured(
            system_prompt=_DYNAMIC_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=AgentResponse,
        )

    async def _apply_agent_response(
        self,
        session: AsyncSession,
        task: Task,
        agent_response: AgentResponse,
        factory: async_sessionmaker[AsyncSession],
        allow_subtasks: bool,
    ) -> Task:
        tool_results, has_pending_approval = await process_tool_calls(
            session=session,
            task=task,
            tool_calls=agent_response.proposed_tool_calls,
            policy_engine=self.policy_engine,
        )

        subtasks = agent_response.subtasks if allow_subtasks else []
        if subtasks:
            depth = await get_task_depth(session, task, self.max_depth)
            if depth >= self.max_depth:
                return await transition_task(
                    session,
                    task,
                    TaskStatus.FAILED,
                    result={"error": f"Max task depth ({self.max_depth}) exceeded when spawning subtasks."},
                )
            spawn_subtasks(session, task, subtasks)

        result_payload = {
            "message": agent_response.message,
            "tool_results": tool_results,
        }

        if has_pending_approval:
            return await transition_task(session, task, TaskStatus.WAITING_APPROVAL, result=result_payload)

        if subtasks:
            await transition_task(session, task, TaskStatus.WAITING_CHILDREN, result=result_payload)
            await self._run_step_group(session, task, factory)
            await session.refresh(task)
            return task

        return await transition_task(session, task, TaskStatus.COMPLETED, result=result_payload)

    async def _run_step_group(
        self,
        session: AsyncSession,
        parent_task: Task,
        factory: async_sessionmaker[AsyncSession],
    ) -> bool:
        return await run_next_step_group(
            session=session,
            parent_task=parent_task,
            run_child=lambda child_id: self._run_child_in_session(child_id, factory),
        )

    async def _run_child_in_session(
        self,
        child_id: str,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with factory() as child_session:
            child = await child_session.get(Task, child_id)
            if child is None:
                return
            await self.run_task(child_session, child, session_factory=factory)

    async def _advance_ancestors(
        self,
        session: AsyncSession,
        task: Task,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        current = task
        while current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) and current.parent_task_id:
            parent = await session.get(Task, current.parent_task_id)
            if not parent or parent.status != TaskStatus.WAITING_CHILDREN:
                break
            finished = await self._run_step_group(session, parent, factory)
            if not finished:
                break
            await session.refresh(parent)
            current = parent

    @staticmethod
    async def _has_pending_approvals(session: AsyncSession, task_id: str) -> bool:
        statement = select(Approval.id).where(
            Approval.task_id == task_id,
            Approval.status == ApprovalStatus.PENDING,
        )
        res = await session.exec(statement)
        return res.first() is not None

    @staticmethod
    def _has_failed_approved_tool(task: Task) -> bool:
        tool_results = safe_json_loads(task.result_json).get("tool_results", [])
        return any(
            isinstance(entry, dict)
            and entry.get("status") == "APPROVED"
            and entry.get("success") is False
            for entry in tool_results
        )
