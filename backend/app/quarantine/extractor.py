"""Quarantine ingestion and deterministic sanitization extractor."""

from email.utils import parseaddr
import html
import re
from typing import Any
from pydantic import BaseModel, Field


class SanitizedEmail(BaseModel):
    sender: str
    sender_name: str = ""
    sender_email: str = ""
    sender_domain: str = ""
    recipient: str = ""
    subject: str
    clean_body: str
    thread_id: str | None = None
    injection_signals: list[str] = Field(default_factory=list)


SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
MAX_BODY_CHARS = 10_000

INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "system_prompt_marker",
        re.compile(
            r"\b(?:system[_\s-]?prompt|developer[_\s-]?prompt|system\s+override|"
            r"ignore\s+(?:all\s+)?(?:prior|previous)\s+instructions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "plain_text_json",
        re.compile(
            r"\{[^{}]*\"[a-zA-Z0-9_]+\"\s*:\s*(?:\"[^\"]*\"|true|false|null|-?\d+(?:\.\d+)?|\{|\[)[^{}]*\}",
            re.IGNORECASE,
        ),
    ),
)


def clean_raw_text(text: str) -> str:
    """Light pre-processing to strip HTML tags, scripts, and excessive length without dropping body text."""
    if not text:
        return ""
    no_scripts = SCRIPT_RE.sub(" ", text)
    no_tags = TAG_RE.sub(" ", no_scripts)
    unescaped = html.unescape(no_tags)
    normalized = " ".join(unescaped.split())
    return normalized[:MAX_BODY_CHARS]


def parse_sender_fields(raw_sender: str) -> tuple[str, str, str, str]:
    """Parse display sender, sender_name, sender_email, and sender_domain from header sender."""
    if not raw_sender or not raw_sender.strip():
        return "", "", "", ""

    raw_name, raw_addr = parseaddr(raw_sender.strip())
    name = clean_raw_text(raw_name)
    addr = clean_raw_text(raw_addr).lower()

    if "@" in addr:
        local, _, domain = addr.rpartition("@")
        if local and domain:
            display = f"{name} <{addr}>" if name else addr
            return display, name, addr, domain

    cleaned = clean_raw_text(raw_sender)
    return cleaned, name or cleaned, "", ""


def detect_injection_signals(text: str) -> list[str]:
    """Detect common prompt-injection markers (e.g. system_prompt, plain-text JSON) without altering text."""
    if not text:
        return []
    return [label for label, pattern in INJECTION_PATTERNS if pattern.search(text)]


class QuarantineExtractor:
    """Normalizes untrusted external payloads and validates SanitizedEmail schemas."""

    def extract_email(self, raw_payload: dict[str, Any]) -> SanitizedEmail:
        raw_thread_id = raw_payload.get("thread_id")
        thread_id = (
            clean_raw_text(str(raw_thread_id))
            if raw_thread_id is not None and str(raw_thread_id).strip()
            else None
        )
        sender, sender_name, sender_email, sender_domain = parse_sender_fields(
            str(raw_payload.get("sender", ""))
        )
        subject = clean_raw_text(str(raw_payload.get("subject", "")))
        clean_body = clean_raw_text(str(raw_payload.get("body", "")))
        injection_signals = detect_injection_signals(f"{subject} {clean_body}")

        return SanitizedEmail(
            sender=sender,
            sender_name=sender_name,
            sender_email=sender_email,
            sender_domain=sender_domain,
            recipient=clean_raw_text(str(raw_payload.get("recipient", ""))),
            subject=subject,
            clean_body=clean_body,
            thread_id=thread_id,
            injection_signals=injection_signals,
        )
