"""E2E smoke test for the retry path: first sandbox run fails, agent drafts a second
patch, second sandbox run passes. Verifies the gate's conditional edge and the
bounded-attempt logic together.
"""

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_sample_repo() -> str:
    tmp = tempfile.mkdtemp(prefix="hivefix-e2e-retry-")
    with open(os.path.join(tmp, "calc.py"), "w") as fh:
        fh.write("def subtract(a, b):\n    return a + b\n")
    return tmp


async def main():
    from app.github import client as github_client_module
    from app.run_manager import run_manager

    repo_path = _write_sample_repo()

    class FakeIssueRef:
        owner = "test-owner"
        repo = "test-repo"
        number = 2
        title = "subtract() is wrong"
        body = "subtract(5, 2) should be 3."

    fake_llm_responses = iter(
        [
            MagicMock(content='{"summary": "bug in subtract", "suspected_symbols": ["subtract"]}'),
            MagicMock(content='{"patch_diff": "--- bad patch 1 ---", "rationale": "attempt 1"}'),
            MagicMock(content='{"patch_diff": "--- good patch 2 ---", "rationale": "attempt 2"}'),
        ]
    )

    sandbox_results = iter(
        [
            {"passed": False, "conclusion": "failure", "run_url": "https://x/1"},
            {"passed": True, "conclusion": "success", "run_url": "https://x/2"},
        ]
    )

    def _fake_clone(self, owner, repo, dest_dir):
        import shutil

        shutil.rmtree(dest_dir, ignore_errors=True)
        shutil.copytree(repo_path, dest_dir)
        return dest_dir

    with patch.object(github_client_module.GitHubClient, "parse_issue_url", return_value=FakeIssueRef()), patch.object(
        github_client_module.GitHubClient, "default_branch_sha", return_value=("main", "deadbeef")
    ), patch.object(github_client_module.GitHubClient, "clone_repo", _fake_clone), patch.object(
        github_client_module.GitHubClient, "dispatch_sandbox_run", return_value="fake-run-token"
    ), patch.object(
        github_client_module.GitHubClient, "poll_sandbox_run", side_effect=lambda *a, **k: next(sandbox_results)
    ), patch.object(
        github_client_module.GitHubClient, "open_pr", return_value="https://github.com/test-owner/test-repo/pull/100"
    ), patch("app.nodes.triage.ChatGroq") as mock_triage_llm, patch(
        "app.nodes.patch.ChatGroq"
    ) as mock_patch_llm, patch(
        "app.nodes.retrieve.ChatGroq"
    ) as mock_retrieve_llm:
        mock_triage_llm.return_value.invoke.side_effect = lambda *a, **k: next(fake_llm_responses)
        mock_patch_llm.return_value.invoke.side_effect = lambda *a, **k: next(fake_llm_responses)
        mock_retrieve_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="No tool calls needed.")
        )

        run_id = await run_manager.start_run("https://github.com/test-owner/test-repo/issues/2")

        for _ in range(100):
            state = await run_manager.get_state(run_id)
            if state and state.get("status") in ("resolved", "failed"):
                break
            await asyncio.sleep(0.1)
        else:
            raise SystemExit("Run did not finish in time")

    assert state["status"] == "resolved", f"expected resolved after retry, got {state}"
    assert state["attempt"] == 2, f"expected 2 patch attempts, got {state['attempt']}"
    patch_entries = [e for e in state["audit_log"] if e["action"] == "draft_patch"]
    assert len(patch_entries) == 2, f"expected 2 draft_patch audit entries, got {patch_entries}"
    sandbox_entries = [e for e in state["audit_log"] if e["action"] == "sandbox_test_run"]
    assert [e["status"] for e in sandbox_entries] == ["failed", "ok"], sandbox_entries

    print("RETRY PATH SMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
