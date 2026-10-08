"""End-to-end smoke test: runs the real LangGraph graph against a real local Redis,
with GitHub and the LLM mocked (no live credentials needed). Verifies the full node
chain, state persistence/streaming, scoped access control, and audit trail together.

Run manually against a local `docker compose up redis qdrant`:
    REDIS_URL=redis://localhost:6379/0 QDRANT_URL=http://localhost:6333 \
    .venv/bin/python tests/test_e2e_smoke.py
"""

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_REPO = {
    "calc.py": """
def add(a, b):
    return a + b

def subtract(a, b):
    # bug: should be a - b
    return a + b
""",
}


def _write_sample_repo() -> str:
    tmp = tempfile.mkdtemp(prefix="hivefix-e2e-")
    for name, content in SAMPLE_REPO.items():
        with open(os.path.join(tmp, name), "w") as fh:
            fh.write(content)
    return tmp


FAKE_PATCH_DIFF = """--- a/calc.py
+++ b/calc.py
@@ -4,4 +4,4 @@ def add(a, b):
 def subtract(a, b):
-    # bug: should be a - b
-    return a + b
+    return a - b
"""


async def main():
    from app.github import client as github_client_module
    from app.identity import ALL_IDENTITIES
    from app.run_manager import run_manager

    repo_path = _write_sample_repo()

    class FakeIssueRef:
        owner = "test-owner"
        repo = "test-repo"
        number = 1
        title = "subtract() returns the wrong value"
        body = "calc.subtract(5, 2) returns 7 instead of 3."

    fake_llm_responses = iter(
        [
            MagicMock(
                content='{"summary": "subtract() adds instead of subtracting.", "suspected_symbols": ["subtract"]}'
            ),
            MagicMock(content=f'{{"patch_diff": {FAKE_PATCH_DIFF!r}, "rationale": "Fixed the operator."}}'),
        ]
    )

    def _fake_clone(self, owner, repo, dest_dir):
        # Mirrors what a real `git clone` would leave behind: dest_dir is the
        # directory the rest of the pipeline reads state["clone_path"] from, not
        # the fixed repo_path fixture — so this must actually populate it.
        import shutil

        shutil.rmtree(dest_dir, ignore_errors=True)
        shutil.copytree(repo_path, dest_dir)
        return dest_dir

    with patch.object(github_client_module.GitHubClient, "parse_issue_url", return_value=FakeIssueRef()), patch.object(
        github_client_module.GitHubClient, "default_branch_sha", return_value=("main", "deadbeef")
    ), patch.object(github_client_module.GitHubClient, "clone_repo", _fake_clone), patch.object(
        github_client_module.GitHubClient, "dispatch_sandbox_run", return_value="fake-run-token"
    ), patch.object(
        github_client_module.GitHubClient,
        "poll_sandbox_run",
        return_value={"passed": True, "conclusion": "success", "run_url": "https://github.com/fake/run/1"},
    ), patch.object(
        github_client_module.GitHubClient, "open_pr", return_value="https://github.com/test-owner/test-repo/pull/99"
    ), patch("app.nodes.triage.ChatGroq") as mock_triage_llm, patch(
        "app.nodes.patch.ChatGroq"
    ) as mock_patch_llm, patch(
        "app.nodes.retrieve.ChatGroq"
    ) as mock_retrieve_llm:
        mock_triage_llm.return_value.invoke.side_effect = lambda *a, **k: next(fake_llm_responses)
        mock_patch_llm.return_value.invoke.side_effect = lambda *a, **k: next(fake_llm_responses)

        # Retrieval LLM: first turn calls the real bm25_search MCP tool (exercising
        # the actual MCP server subprocess), second turn stops (no more tool calls).
        retrieve_turns = iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "bm25_search", "args": {"query": "subtract", "k": 5}, "id": "call_1"}],
                ),
                AIMessage(content="Localized to subtract()."),
            ]
        )
        mock_retrieve_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(
            side_effect=lambda *a, **k: next(retrieve_turns)
        )

        run_id = await run_manager.start_run("https://github.com/test-owner/test-repo/issues/1")
        print(f"run_id={run_id}")

        for _ in range(100):
            state = await run_manager.get_state(run_id)
            if state and state.get("status") in ("resolved", "failed"):
                break
            await asyncio.sleep(0.1)
        else:
            raise SystemExit("Run did not finish in time")

    assert state["status"] == "resolved", f"expected resolved, got {state}"
    assert state["pr_url"] == "https://github.com/test-owner/test-repo/pull/99"
    assert state["sandbox_result"]["passed"] is True

    retrieve_entry = next(e for e in state["audit_log"] if e["action"] == "retrieve_context")
    bm25_call = retrieve_entry["detail"]["mcp_tool_calls"][0]
    assert bm25_call["result_count"] > 0, (
        "bm25_search over the real cloned repo found nothing for a query that "
        f"should match subtract() directly — retrieval is silently running against "
        f"an empty or wrong directory: {retrieve_entry}"
    )
    assert any(h.get("symbol") == "subtract" for h in state["retrieval_hits"]), state["retrieval_hits"]

    audit_identities = [e["identity"] for e in state["audit_log"]]
    expected_identities = [i.name for i in ALL_IDENTITIES if i.name != "hivefix-gate"]
    assert audit_identities == expected_identities, f"audit trail mismatch: {audit_identities}"

    print("audit trail:", audit_identities)
    print("E2E SMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
