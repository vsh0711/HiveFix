"""Shared helpers for parsing structured LLM output. Several open-weight models
(Qwen among them) wrap JSON responses in a markdown code fence even when told to
respond with JSON only — naive json.loads() breaks on that, so every node that asks
for structured output should go through this instead."""

import json
import re

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


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
