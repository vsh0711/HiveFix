import json

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from .. import identity
from ..audit import append_audit, audit_event
from ..config import settings
from ..models.state import RunState

_SYSTEM = """You triage GitHub issues for an autonomous bug-fix agent. Given an issue
title and body, identify:
1. A one-paragraph summary of the actual bug/behavior being reported.
2. A list of likely function/class/method names (just the bare identifiers, as they'd
   appear in code) that are probably involved, based on stack traces, error messages,
   or described behavior in the issue text.

Respond ONLY with JSON: {"summary": str, "suspected_symbols": [str, ...]}"""


def triage_node(state: RunState) -> RunState:
    node_identity = identity.TRIAGE
    llm = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Title: {state['issue_title']}\n\nBody:\n{state['issue_body']}"),
    ]
    response = llm.invoke(
        messages,
        config={
            "tags": [node_identity.name],
            "run_name": node_identity.name,
            "metadata": {"run_id": state["run_id"], "node": node_identity.name},
        },
    )
    try:
        parsed = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        parsed = {"summary": response.content, "suspected_symbols": []}

    entry = audit_event(
        node_identity,
        action="triage_issue",
        detail={"suspected_symbols": parsed.get("suspected_symbols", [])},
    )

    return {
        **state,
        "triage_summary": parsed.get("summary", ""),
        "suspected_symbols": parsed.get("suspected_symbols", []),
        "status": "triaged",
        "audit_log": append_audit(state, entry),
    }
