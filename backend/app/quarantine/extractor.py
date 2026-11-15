"""Quarantine ingestion and deterministic sanitization extractor."""

import html
import re
from typing import Any
from pydantic import BaseModel


class SanitizedEmail(BaseModel):
    sender: str
    recipient: str = ""
    subject: str
    clean_body: str
    thread_id: str | None = None


SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
MAX_BODY_CHARS = 10_000


def clean_raw_text(text: str) -> str:
    """Deterministic pre-processing to strip HTML tags, scripts, and excessive length."""
    if not text:
        return ""
    no_scripts = SCRIPT_RE.sub(" ", text)
    no_tags = TAG_RE.sub(" ", no_scripts)
    unescaped = html.unescape(no_tags)
    normalized = " ".join(unescaped.split())
    return normalized[:MAX_BODY_CHARS]


class QuarantineExtractor:
    """Normalizes untrusted external payloads and validates SanitizedEmail schemas."""

    def extract_email(self, raw_payload: dict[str, Any]) -> SanitizedEmail:
        raw_thread_id = raw_payload.get("thread_id")
        thread_id = (
            clean_raw_text(str(raw_thread_id))
            if raw_thread_id is not None and str(raw_thread_id).strip()
            else None
        )

        return SanitizedEmail(
            sender=clean_raw_text(str(raw_payload.get("sender", ""))),
            recipient=clean_raw_text(str(raw_payload.get("recipient", ""))),
            subject=clean_raw_text(str(raw_payload.get("subject", ""))),
            clean_body=clean_raw_text(str(raw_payload.get("body", ""))),
            thread_id=thread_id,
        )
