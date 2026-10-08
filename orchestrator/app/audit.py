"""Structured audit trail: who (identity) did what (action) to what (target), with
what result, on every run. Independent of the LangSmith trace — this is the record a
non-technical reviewer or an incident review can read without LangSmith access.

Each node appends one entry to RunState["audit_log"] before returning. The run state
(and therefore the audit log) is already persisted to Redis and streamed to the
dashboard by run_manager on every node completion, so no separate storage is needed.
"""

import time

from .identity import NodeIdentity


def audit_event(identity: NodeIdentity, action: str, detail: dict, status: str = "ok") -> dict:
    return {
        "ts": time.time(),
        "identity": identity.name,
        "action": action,
        "status": status,
        "detail": detail,
    }


def append_audit(state: dict, entry: dict) -> list[dict]:
    return [*state.get("audit_log", []), entry]
