"""GitHub integration: fetch issues, clone repos, dispatch + poll the sandbox-test
workflow in THIS repo (HiveFix), and open PRs on the target repo.
"""

import base64
import re
import time
import uuid
from dataclasses import dataclass

import git
from github import Github

from ..config import settings


@dataclass
class IssueRef:
    owner: str
    repo: str
    number: int
    title: str
    body: str


_ISSUE_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")


class GitHubClient:
    def __init__(self):
        self._gh = Github(settings.github_token) if settings.github_token else Github()

    def parse_issue_url(self, issue_url: str) -> IssueRef:
        m = _ISSUE_URL_RE.search(issue_url)
        if not m:
            raise ValueError(f"Not a GitHub issue URL: {issue_url}")
        owner, repo, number = m.group(1), m.group(2), int(m.group(3))
        gh_repo = self._gh.get_repo(f"{owner}/{repo}")
        issue = gh_repo.get_issue(number)
        return IssueRef(owner=owner, repo=repo, number=number, title=issue.title, body=issue.body or "")

    def clone_repo(self, owner: str, repo: str, dest_dir: str) -> str:
        url = f"https://github.com/{owner}/{repo}.git"
        git.Repo.clone_from(url, dest_dir, depth=1)
        return dest_dir

    def default_branch_sha(self, owner: str, repo: str) -> tuple[str, str]:
        gh_repo = self._gh.get_repo(f"{owner}/{repo}")
        branch = gh_repo.default_branch
        sha = gh_repo.get_branch(branch).commit.sha
        return branch, sha

    # --- sandbox dispatch (runs on HiveFix's own repo's Actions) ---

    def dispatch_sandbox_run(
        self,
        target_repo_url: str,
        base_ref: str,
        patch_diff: str,
        test_command: str,
    ) -> str:
        """Triggers .github/workflows/sandbox-test.yml via workflow_dispatch, tagged
        with a unique run token so we can find the resulting run."""
        if not settings.hivefix_repo:
            raise RuntimeError("HIVEFIX_REPO is not set")
        hivefix_repo = self._gh.get_repo(settings.hivefix_repo)
        run_token = uuid.uuid4().hex
        patch_b64 = base64.b64encode(patch_diff.encode("utf-8")).decode("ascii")

        workflow = hivefix_repo.get_workflow("sandbox-test.yml")
        workflow.create_dispatch(
            ref=hivefix_repo.default_branch,
            inputs={
                "repo_url": target_repo_url,
                "base_ref": base_ref,
                "patch_b64": patch_b64,
                "test_command": test_command,
                "run_token": run_token,
            },
        )
        return run_token

    def poll_sandbox_run(self, run_token: str, interval: int, timeout: int) -> dict:
        """Polls HiveFix's Actions runs for the one tagged with run_token, waits for
        completion, and returns {passed, conclusion, run_url}."""
        if not settings.hivefix_repo:
            raise RuntimeError("HIVEFIX_REPO is not set")
        hivefix_repo = self._gh.get_repo(settings.hivefix_repo)
        deadline = time.time() + timeout
        matched_run = None

        while time.time() < deadline:
            runs = hivefix_repo.get_workflow("sandbox-test.yml").get_runs()
            for run in runs[:10]:
                if run_token in (run.display_title or "") or run_token in (run.name or ""):
                    matched_run = run
                    break
            if matched_run is None:
                time.sleep(interval)
                continue

            matched_run.update()
            if matched_run.status == "completed":
                return {
                    "passed": matched_run.conclusion == "success",
                    "conclusion": matched_run.conclusion,
                    "run_url": matched_run.html_url,
                }
            time.sleep(interval)

        return {"passed": False, "conclusion": "timeout", "run_url": None}

    # --- PR creation ---

    def open_pr(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        branch_name: str,
        patch_diff: str,
        title: str,
        body: str,
    ) -> str:
        gh_repo = self._gh.get_repo(f"{owner}/{repo}")
        base_sha = gh_repo.get_branch(base_branch).commit.sha
        gh_repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_sha)

        # Apply the unified diff locally against a fresh clone, then push.
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            local = git.Repo.clone_from(f"https://github.com/{owner}/{repo}.git", tmp, branch=branch_name)
            patch_path = f"{tmp}/.hivefix.patch"
            with open(patch_path, "w") as fh:
                fh.write(patch_diff)
            subprocess.run(["git", "apply", "--whitespace=fix", patch_path], cwd=tmp, check=True)
            local.git.add(A=True)
            local.index.commit("HiveFix: automated patch")
            local.git.push("origin", branch_name)

        pr = gh_repo.create_pull(title=title, body=body, head=branch_name, base=base_branch)
        return pr.html_url
