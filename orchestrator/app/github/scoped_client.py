"""Wraps GitHubClient so a node can only call the GitHub actions its NodeIdentity
allows. This turns the identity.py allowlists from documentation into something that
actually throws if a node drifts outside its scope (e.g. a future edit to patch_node
that tries to call open_pr directly)."""

from ..identity import NodeIdentity
from .client import GitHubClient


class ScopedPermissionError(PermissionError):
    pass


class ScopedGitHubClient:
    def __init__(self, identity: NodeIdentity, client: GitHubClient | None = None):
        self._identity = identity
        self._client = client or GitHubClient()

    def _check(self, action: str):
        if action not in self._identity.allowed_github_actions:
            raise ScopedPermissionError(
                f"identity '{self._identity.name}' is not permitted to call '{action}' "
                f"(allowed: {sorted(self._identity.allowed_github_actions)})"
            )

    def parse_issue_url(self, *args, **kwargs):
        # Read-only metadata lookup needed by every identity that touches an issue;
        # exempt from the write-action allowlist.
        return self._client.parse_issue_url(*args, **kwargs)

    def clone_repo(self, *args, **kwargs):
        return self._client.clone_repo(*args, **kwargs)

    def default_branch_sha(self, *args, **kwargs):
        return self._client.default_branch_sha(*args, **kwargs)

    def dispatch_sandbox_run(self, *args, **kwargs):
        self._check("dispatch_sandbox_run")
        return self._client.dispatch_sandbox_run(*args, **kwargs)

    def poll_sandbox_run(self, *args, **kwargs):
        self._check("poll_sandbox_run")
        return self._client.poll_sandbox_run(*args, **kwargs)

    def open_pr(self, *args, **kwargs):
        self._check("open_pr")
        return self._client.open_pr(*args, **kwargs)
