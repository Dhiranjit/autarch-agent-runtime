"""Lightweight semi-deterministic StateGraph workflow runner."""

from collections.abc import Awaitable, Callable
import inspect
from typing import Any
from pydantic import BaseModel

from app.core.models import RiskLevel
from app.events.bus import default_event_bus
from app.tools.registry import Tool

END = "__end__"

type NodeFn[StateT: BaseModel] = Callable[[StateT], StateT | Awaitable[StateT]]
type RouterFn[StateT: BaseModel] = Callable[[StateT], str]


class StateGraph[StateT: BaseModel]:
    """Deterministic / conditional state machine for predefined modules (e.g. email_ingestion)."""

    def __init__(self, name: str, state_cls: type[StateT]) -> None:
        self.name = name
        self.state_cls = state_cls
        self._nodes: dict[str, NodeFn[StateT]] = {}
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[str, RouterFn[StateT]] = {}
        self._entry_point: str | None = None

    def add_node(self, name: str, fn: NodeFn[StateT]) -> "StateGraph[StateT]":
        """Register a named processing node."""
        if name == END:
            raise ValueError(f"Node name cannot be reserved sentinel '{END}'.")
        self._nodes[name] = fn
        if self._entry_point is None:
            self._entry_point = name
        return self

    def set_entry_point(self, name: str) -> "StateGraph[StateT]":
        """Explicitly set the starting node of the graph."""
        self._entry_point = name
        return self

    def add_edge(self, start_node: str, end_node: str) -> "StateGraph[StateT]":
        """Add a deterministic directed transition from start_node to end_node."""
        self._edges[start_node] = end_node
        return self

    def add_conditional_edge(
        self,
        start_node: str,
        router: RouterFn[StateT],
    ) -> "StateGraph[StateT]":
        """Add a state-dependent transition out of start_node."""
        self._conditional_edges[start_node] = router
        return self

    async def run(
        self,
        initial_state: StateT,
        task_id: str | None = None,
        max_transitions: int = 25,
    ) -> StateT:
        """Execute the state graph from entry_point until END."""
        if self._entry_point is None:
            raise RuntimeError(f"StateGraph '{self.name}' has no entry point configured.")

        current_node = self._entry_point
        state = initial_state
        steps = 0

        while current_node != END:
            steps += 1
            if steps > max_transitions:
                raise RuntimeError(
                    f"StateGraph '{self.name}' exceeded max_transitions ({max_transitions})."
                )

            node_fn = self._nodes.get(current_node)
            if node_fn is None:
                raise RuntimeError(
                    f"Node '{current_node}' is not registered in StateGraph '{self.name}'."
                )

            await default_event_bus.publish(
                "workflow_step",
                {
                    "task_id": task_id,
                    "workflow": self.name,
                    "node": current_node,
                    "status": "started",
                },
            )

            result = node_fn(state)
            if inspect.isawaitable(result):
                state = await result
            else:
                state = result

            await default_event_bus.publish(
                "workflow_step",
                {
                    "task_id": task_id,
                    "workflow": self.name,
                    "node": current_node,
                    "status": "completed",
                },
            )

            if current_node in self._conditional_edges:
                current_node = self._conditional_edges[current_node](state)
            elif current_node in self._edges:
                current_node = self._edges[current_node]
            else:
                current_node = END

        return state

    def as_tool(
        self,
        name: str,
        description: str,
        parameters: type[BaseModel],
        state_builder: Callable[..., StateT],
        output_extractor: Callable[[StateT], Any] | None = None,
        risk_level: RiskLevel = RiskLevel.LEVEL_0,
    ) -> Tool:
        """Expose this StateGraph workflow as an individual named Tool for the Orchestrator."""

        async def _run_workflow_tool(**kwargs: Any) -> Any:
            initial_state = state_builder(**kwargs)
            final_state = await self.run(initial_state=initial_state)
            if output_extractor is not None:
                return output_extractor(final_state)
            return final_state.model_dump()

        return Tool(
            name=name,
            description=description,
            parameters=parameters,
            risk_level=risk_level,
            func=_run_workflow_tool,
        )
