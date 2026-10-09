"""Shared helpers for LLM calls: robust JSON parsing and rate-limit retry.

Several open-weight models (Qwen among them) wrap JSON responses in a markdown code
fence even when told to respond with JSON only — naive json.loads() breaks on that,
so every node that asks for structured output should go through parse_json_response.

Groq's free tier enforces a per-minute output-token cap (1000 OTPM observed on
qwen/qwen3.8-27b) well within what this pipeline's combined calls can need in a
single run — invoke_with_retry/ainvoke_with_retry back off and retry on that rather
than failing the whole run over a transient quota window.
"""

import json
import re
import time

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)

_RATE_LIMIT_MARKERS = ("rate_limit_exceeded", "429", "rate limit")
_RATE_LIMIT_WAIT_SECONDS = 70  # clears a per-minute window with margin
_RATE_LIMIT_MAX_ATTEMPTS = 3


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def invoke_with_retry(llm, messages, **kwargs):
    for attempt in range(1, _RATE_LIMIT_MAX_ATTEMPTS + 1):
        try:
            return llm.invoke(messages, **kwargs)
        except Exception as exc:
            if attempt == _RATE_LIMIT_MAX_ATTEMPTS or not _is_rate_limit_error(exc):
                raise
            time.sleep(_RATE_LIMIT_WAIT_SECONDS)


async def ainvoke_with_retry(llm, messages, **kwargs):
    import asyncio

    for attempt in range(1, _RATE_LIMIT_MAX_ATTEMPTS + 1):
        try:
            return await llm.ainvoke(messages, **kwargs)
        except Exception as exc:
            if attempt == _RATE_LIMIT_MAX_ATTEMPTS or not _is_rate_limit_error(exc):
                raise
            await asyncio.sleep(_RATE_LIMIT_WAIT_SECONDS)


def parse_json_response(content: str) -> dict | None:
    """Parses a JSON object out of raw LLM output, stripping a markdown code fence
    if present. Returns None if no valid JSON object could be extracted."""
    text = content.strip()
    fence_match = _CODE_FENCE_RE.match(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Last resort: the model added prose before/after the JSON object — grab the
    # outermost {...} span.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
