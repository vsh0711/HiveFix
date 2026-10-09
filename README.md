# HiveFix

Autonomous bug-resolution agent: takes a GitHub issue from triage to a merge-ready pull request, with no human edits in the loop. Built on LangGraph, with every patch gated behind a Docker-sandboxed regression run before a PR is opened.

Persona: **Buzz** — the HiveFix bee. The dashboard visualizes each run as Buzz flying between stages (scout → trail → pollinate → hive-check → honey delivered). PRs and commit messages themselves stay plain/professional; the persona lives only in the dashboard UI.

## Scope (v1)

- Target repos: **Python** only (retrieval/AST call-graph tooling is Python-specific for v1)
- One issue → one run → one PR attempt loop, with a bounded retry count on sandbox failure

## Architecture

```
GitHub issue URL
      │
      ▼
 ┌─────────┐   ┌───────────┐   ┌──────────┐   ┌─────────────┐   ┌──────┐   ┌────────┐
 │ Triage  │──▶│ Retrieve  │──▶│  Patch   │──▶│   Sandbox    │──▶│ Gate │──▶│ Open PR│
 │ (LLM)   │   │ BM25 +    │   │  draft   │   │ dispatch     │   │      │   │ (PR)   │
 │         │   │ AST call- │   │  (LLM)   │   │ (GH Actions  │   │      │   │        │
 │         │   │ graph MCP │   │          │   │  + Docker)   │   │      │   │        │
 │         │   │ + Qdrant  │   │          │   │              │   │      │   │        │
 └─────────┘   └───────────┘   └──────────┘   └─────────────┘   └──┬───┘   └────────┘
                                     ▲                               │ fail, retries left
                                     └───────────────────────────────┘
```

- **LangGraph** orchestrates the state machine above (`orchestrator/app/graph`).
- **LangChain** (+ Groq, free-tier inference — default model `qwen/qwen3.8-27b`) drives triage, retrieval tool-calling, and patch drafting.
- **MCP tools** (`orchestrator/app/mcp_tools`) expose BM25 code search and AST call-graph traversal to the agent for fault localization.
- **Qdrant** holds embedded code chunks as a semantic-search fallback alongside BM25.
- **Redis** stores run state/events for the dashboard and acts as the run queue.
- **LangSmith** traces every graph run end-to-end.
- **RAGAS** (`orchestrator/app/eval`) scores patch groundedness against retrieved context offline, over a sampled issue set.
- **Docker** sandboxed regression runs happen via a GitHub Actions workflow (`.github/workflows/sandbox-test.yml`) dispatched by the orchestrator against the target repo — GitHub-hosted runners have Docker natively and are free for public repos.
- **Frontend** (`frontend/`) is a live dashboard showing Buzz move through the stages of a run, with diff and sandbox log viewers.

## Agent identity, access & traceability

HiveFix is deliberately **one agent, one LangGraph process, one set of credentials** —
not a multi-agent swarm — but every node still acts under its own scoped identity
(`orchestrator/app/identity.py`), enforced rather than documentation-only:

| Node | Identity | Can do | Cannot do |
|---|---|---|---|
| triage | `hivefix-triage` | Read issue text, call the LLM | Nothing else |
| retrieve | `hivefix-retriever` | `bm25_search`, `callgraph_lookup`, `qdrant_search` (all read-only) | No repo writes, no sandbox dispatch |
| patch | `hivefix-patcher` | Draft a diff from context | No execution, no repo access |
| sandbox | `hivefix-verifier` | Dispatch + poll the sandbox-test workflow | No target-repo write access |
| gate | `hivefix-gate` | Decide retry / publish / abort | No external access |
| open_pr | `hivefix-publisher` | **The only identity that can branch/push/open a PR** | Nothing upstream of a passing sandbox run |

`ScopedGitHubClient` (`orchestrator/app/github/scoped_client.py`) enforces this: each
node constructs a client bound to its own `NodeIdentity`, and a call outside that
identity's `allowed_github_actions` raises `ScopedPermissionError` rather than
silently succeeding. `GITHUB_TOKEN` itself should be a fine-grained PAT scoped only to
HiveFix's own repo (for Actions dispatch) and the target repos it's permitted to open
PRs against — the code-level scoping is defense in depth, not a substitute for that.

**Approval model:** fully autonomous, matching the original goal of issue-to-PR with
no human edits in the loop. The human checkpoint is the PR review itself, not a gate
inside the agent. Safety instead comes from: a bounded retry count
(`MAX_PATCH_ATTEMPTS`), every patch being gated behind a real sandboxed test run
before a PR can be opened at all, and the publisher identity having no path to a PR
except through a passing `sandbox` result.

**Traceability:** every node appends a structured entry — identity, action, status,
detail — to `RunState["audit_log"]`, which is persisted and streamed to the dashboard
like the rest of the run state (`GET /runs/{run_id}` returns it; no separate store).
Every LLM call also carries the node's identity as a LangSmith tag/run-name, so the
audit log (what happened) and the LangSmith trace (why — full prompts/completions)
cross-reference by identity + run_id.

## Local dev

```bash
cp .env.example .env   # fill in GROQ_API_KEY, GITHUB_TOKEN, etc.
docker compose up --build
```

- Orchestrator API: http://localhost:8000
- Qdrant: http://localhost:6333
- Redis: localhost:6379
- Frontend: http://localhost:3000

## Known limitation: Groq free-tier rate limits

`qwen/qwen3.8-27b` on Groq's free tier caps output tokens at 1000/minute, which a
single HiveFix run can exceed on its own (triage + up to 4 retrieval tool-calling
turns + patch drafting, each a real LLM call). `app/llm_utils.py`'s
`invoke_with_retry`/`ainvoke_with_retry` back off ~70s and retry (up to 3 attempts)
on a detected rate-limit error rather than failing the run outright, but a run can
still take several minutes longer than it otherwise would under sustained load.
Groq's paid tiers raise this limit substantially if throughput matters more than
cost for a given deployment.

## Deployment

- Orchestrator API + Redis + Qdrant: free tiers (Render + Redis Cloud + Qdrant Cloud) — see `docs/deployment.md`.
- Sandboxed test execution: dispatched as a `workflow_dispatch` run on **this** repo's Actions (`.github/workflows/sandbox-test.yml`), which clones the target repo, applies the candidate patch, and runs its test suite inside Docker. The orchestrator polls the run via the GitHub API rather than relying on a callback.
