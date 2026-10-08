import uuid

from .. import identity
from ..audit import append_audit, audit_event
from ..github.scoped_client import ScopedGitHubClient
from ..models.state import RunState


def open_pr_node(state: RunState) -> RunState:
    node_identity = identity.OPEN_PR
    client = ScopedGitHubClient(node_identity)
    branch_name = f"hivefix/issue-{state['issue_url'].rstrip('/').split('/')[-1]}-{uuid.uuid4().hex[:6]}"

    pr_body = (
        f"Resolves {state['issue_url']}\n\n"
        f"**Summary**\n{state['triage_summary']}\n\n"
        f"**Fix rationale**\n{state['patch_rationale']}\n\n"
        f"**Sandbox regression run:** {state['sandbox_result']['run_url']}\n\n"
        "_Opened autonomously by HiveFix — no human edits in the loop._"
    )

    pr_url = client.open_pr(
        owner=state["repo_owner"],
        repo=state["repo_name"],
        base_branch=state["base_ref"],
        branch_name=branch_name,
        patch_diff=state["patch_diff"],
        title=f"Fix: {state['triage_summary'][:72]}",
        body=pr_body,
    )

    entry = audit_event(node_identity, action="open_pull_request", detail={"pr_url": pr_url, "branch": branch_name})

    return {**state, "pr_url": pr_url, "status": "resolved", "audit_log": append_audit(state, entry)}


def fail_node(state: RunState) -> RunState:
    entry = audit_event(
        identity.GATE,
        action="abort_run",
        detail={"reason": "exhausted_patch_attempts", "attempts": state.get("attempt", 0)},
        status="failed",
    )
    return {
        **state,
        "status": "failed",
        "error": "Exhausted patch attempts without a passing sandbox run.",
        "audit_log": append_audit(state, entry),
    }
