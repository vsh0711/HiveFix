"""Per-node identity and access scoping for the HiveFix agent.

HiveFix runs as one LangGraph process under one set of credentials, but each node
acts under its own logical identity with an explicit, enforced allowlist of actions.
This is what lets a single-agent design still answer "who did what, with what
access" per step — the identity and allowed_actions below are attached to every
LLM call (as LangSmith tags/metadata) and every GitHub/tool call (enforced by
ScopedGitHubClient, see app/github/scoped_client.py).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeIdentity:
    name: str
    description: str
    allowed_github_actions: frozenset[str]
    allowed_mcp_tools: frozenset[str]


TRIAGE = NodeIdentity(
    name="hivefix-triage",
    description="Reads the issue text only. No repo write access, no tool access.",
    allowed_github_actions=frozenset(),
    allowed_mcp_tools=frozenset(),
)

RETRIEVE = NodeIdentity(
    name="hivefix-retriever",
    description="Read-only code search: BM25, AST call-graph, Qdrant similarity.",
    allowed_github_actions=frozenset(),
    allowed_mcp_tools=frozenset({"bm25_search", "callgraph_lookup", "qdrant_search"}),
)

PATCH = NodeIdentity(
    name="hivefix-patcher",
    description="Drafts a unified diff from retrieved context. No execution or repo access.",
    allowed_github_actions=frozenset(),
    allowed_mcp_tools=frozenset(),
)

SANDBOX = NodeIdentity(
    name="hivefix-verifier",
    description="Dispatches the sandbox-test workflow on HiveFix's own repo and polls it. "
    "No access to the target repo beyond a read-only clone performed by the workflow itself.",
    allowed_github_actions=frozenset({"dispatch_sandbox_run", "poll_sandbox_run"}),
    allowed_mcp_tools=frozenset(),
)

OPEN_PR = NodeIdentity(
    name="hivefix-publisher",
    description="The only identity with write access to the target repo: branch, push, open PR.",
    allowed_github_actions=frozenset({"open_pr"}),
    allowed_mcp_tools=frozenset(),
)

GATE = NodeIdentity(
    name="hivefix-gate",
    description="Decides retry vs. publish vs. abort based on the sandbox result. No external access.",
    allowed_github_actions=frozenset(),
    allowed_mcp_tools=frozenset(),
)

ALL_IDENTITIES = [TRIAGE, RETRIEVE, PATCH, SANDBOX, OPEN_PR, GATE]
