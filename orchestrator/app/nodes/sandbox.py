from .. import identity
from ..audit import append_audit, audit_event
from ..config import settings
from ..github.scoped_client import ScopedGitHubClient
from ..models.state import RunState


def sandbox_node(state: RunState) -> RunState:
    node_identity = identity.SANDBOX
    client = ScopedGitHubClient(node_identity)

    run_token = client.dispatch_sandbox_run(
        target_repo_url=state["repo_url"],
        base_ref=state["base_ref"],
        patch_diff=state["patch_diff"],
        test_command=state.get("test_command", "pytest -q"),
    )
    result = client.poll_sandbox_run(
        run_token,
        interval=settings.sandbox_poll_interval_seconds,
        timeout=settings.sandbox_poll_timeout_seconds,
    )

    sandbox_result = {
        "passed": result["passed"],
        "conclusion": result["conclusion"],
        "run_url": result["run_url"],
        "summary": "Tests passed." if result["passed"] else f"Tests failed ({result['conclusion']}).",
    }

    entry = audit_event(
        node_identity,
        action="sandbox_test_run",
        detail={"run_token": run_token, "conclusion": result["conclusion"], "run_url": result["run_url"]},
        status="ok" if result["passed"] else "failed",
    )

    return {**state, "sandbox_result": sandbox_result, "status": "tested", "audit_log": append_audit(state, entry)}
