"""In-memory event bus for broadcasting real-time SSE deltas."""

import asyncio
from collections.abc import AsyncGenerator
import json
from typing import Any
from app.core.models import EventEnvelope


class EventBus:
    """Async fan-out event bus for SSE distribution."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        envelope = EventEnvelope(event_type=event_type, payload=payload)
        data_str = json.dumps(envelope.model_dump(mode="json"))

        # Broadcast to all active queues
        dead_subscribers = set()
        for queue in self._subscribers:
            try:
                queue.put_nowait({"event": event_type, "data": data_str})
            except asyncio.QueueFull:
                dead_subscribers.add(queue)

        for dead in dead_subscribers:
            self._subscribers.discard(dead)

    async def subscribe(self) -> AsyncGenerator[dict[str, str], None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                msg = await queue.get()
                yield msg
        finally:
            self._subscribers.discard(queue)


# Global default EventBus instance
default_event_bus = EventBus()

