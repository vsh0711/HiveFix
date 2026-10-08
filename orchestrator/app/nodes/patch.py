import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from .. import identity
from ..audit import append_audit, audit_event
from ..config import settings
from ..models.state import RunState

_SYSTEM = """You are a senior engineer fixing a bug. You are given an issue summary,
retrieved code context (file paths + snippets), and — on retry — the previous patch's
test failure output. Produce a minimal fix as a single unified diff (git apply
--whitespace=fix compatible), touching only the files necessary.

Respond ONLY with JSON: {"patch_diff": str, "rationale": str}
`patch_diff` must be a valid unified diff starting with `--- a/<path>` / `+++ b/<path>`
headers for each file changed."""


def patch_node(state: RunState) -> RunState:
    node_identity = identity.PATCH
    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", api_key=settings.anthropic_api_key, temperature=0)

    context_block = "\n\n".join(
        f"# {h['file_path']} ({h.get('symbol') or 'module'})\n{h['snippet']}" for h in state.get("retrieval_hits", [])
    )

    retry_block = ""
    prior = state.get("sandbox_result")
    if prior and not prior.get("passed"):
        retry_block = (
            f"\n\nThe previous patch failed the sandbox test run "
            f"(conclusion: {prior.get('conclusion')}). Previous patch:\n{state.get('patch_diff', '')}\n"
            "Produce a different, corrected patch."
        )

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(
            content=(
                f"Issue summary:\n{state['triage_summary']}\n\n"
                f"Retrieved context:\n{context_block}"
                f"{retry_block}"
            )
        ),
    ]
    response = llm.invoke(
        messages,
        config={
            "tags": [node_identity.name],
            "run_name": node_identity.name,
            "metadata": {"run_id": state["run_id"], "node": node_identity.name, "attempt": state.get("attempt", 0) + 1},
        },
    )

    try:
        parsed = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        parsed = {"patch_diff": "", "rationale": response.content}

    attempt = state.get("attempt", 0) + 1
    entry = audit_event(
        node_identity,
        action="draft_patch",
        detail={"attempt": attempt, "diff_lines": len(parsed.get("patch_diff", "").splitlines())},
        status="ok" if parsed.get("patch_diff") else "empty_patch",
    )

    return {
        **state,
        "patch_diff": parsed.get("patch_diff", ""),
        "patch_rationale": parsed.get("rationale", ""),
        "attempt": attempt,
        "status": "patched",
        "audit_log": append_audit(state, entry),
    }
