"""Builtin mock tool providers for Milestone 1."""

from typing import Any
import uuid


class MockEmailProvider:
    """In-memory mock email sender."""

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    async def send_email(self, to: str, subject: str, body: str) -> dict[str, Any]:
        result = {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "to": to,
            "subject": subject,
            "body": body,
            "status": "sent",
        }
        self.sent_emails.append(result)
        return result


class MockTaskProvider:
    """In-memory mock task creator."""

    def __init__(self) -> None:
        self.created_tasks: list[dict[str, Any]] = []

    async def create_task(self, title: str, description: str | None = None) -> dict[str, Any]:
        result = {
            "id": f"task_{uuid.uuid4().hex[:8]}",
            "title": title,
            "description": description or "",
            "status": "created",
        }
        self.created_tasks.append(result)
        return result


# Global default instances for standard gateway execution
mock_email_provider = MockEmailProvider()
mock_task_provider = MockTaskProvider()

