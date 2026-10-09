# Technical findings

Real results, real bugs, and the deliberate tradeoffs behind HiveFix — gathered by
actually running the system against a live demo repo
([vsh0711/hivefix-demo-calc](https://github.com/vsh0711/hivefix-demo-calc)) and a
real deployment, not from code review alone.

## Quantitative results

Ten distinct, deliberately-planted bugs across six categories were run through the
full pipeline end-to-end (real LLM, real MCP tool-calling retrieval, real GitHub
Actions sandbox, real PR):

| Issue | Bug type | Result |
|---|---|---|
| `subtract()` uses `+` instead of `-` | wrong operator | **resolved** |
| `is_positive(0)` returns `True` | boundary/comparison | **resolved** |
| `factorial(5)` returns `24` not `120` | off-by-one loop | **resolved** |
| `divide(7, 2)` returns `3` not `3.5` | wrong operator (`//` vs `/`) | **resolved** |
| `max_of(3, 9)` returns `3` not `9` | inverted comparison branches | **resolved*** |
| `remainder(7, 2)` returns `3` not `1` | wrong operator (`//` vs `%`) | **resolved** |
| `format_price(9.5)` returns `'$9.5'` | wrong format spec (`.1f` vs `.2f`) | **resolved** |
| `unique_items(...)` doesn't preserve order | wrong data structure (`set` vs ordered dedup) | **resolved** |
| `safe_divide(5, 0)` raises instead of returning `None` | wrong exception type caught | **resolved** |
| `all_positive([1,2,-3,4])` returns `True` | wrong boolean aggregation (`any` vs `all`) | **resolved** |

**10/10 resolved**, every merged PR a minimal, correct diff — no extraneous changes.
**0% false-approval rate held across every attempt on every issue**: no incorrect
patch was ever merged, because the sandboxed test gate rejected every wrong patch
before a PR could open.

\* `max_of` is the one genuinely interesting result, not a clean pass. On its first
two attempts (before a prompt fix — see "real issues found" below) the patch
confidently restructured the `if` branch to `return a` in both paths — a different
wrong answer each time, read as a plausible fix by the model's own rationale text,
but never correct. The sandboxed gate caught it both times and correctly refused to
open a PR. After adding an explicit self-trace-against-the-reproduction step to the
patch prompt, a **repeat run of the exact same issue** (not a fresh, easier case)
resolved it correctly on attempt 2. That's the real story: a genuine model reasoning
gap, a safety gate that did its job twice before the gap was closed, and a measurable
fix — not "it worked on the first try."

Caveat: ten bugs (six of them single-line) in one small demo repo is enough to
validate the pipeline, exercise six distinct bug categories, and produce an honest
number — not enough to claim a general resolve rate. See
[eval_results.md](eval_results.md) for the same caveat applied to the RAGAS numbers,
and its note on what a representative-scale eval (e.g. SWE-bench-style sampling)
would take.

### RAGAS (see [eval_results.md](eval_results.md) for full methodology)

| Metric | Result |
|---|---|
| `context_precision` | ~1.0 across all evaluated runs — retrieval is consistently relevant |
| `context_recall` | 0.43–1.0 — lower when retrieval also pulled in unrelated sibling functions |
| `faithfulness` | Low (0.0–0.4) despite objectively correct, test-passing, merged patches — a metric-fit mismatch: RAGAS extracts natural-language "claims" from the answer, and a unified diff isn't phrased as verifiable claims. Not a quality signal for this pipeline's output shape. |

## Real technical issues found and fixed

Each of these was found by running the system for real, not by reading the code.

1. **GitHub Actions script injection.** The sandbox-test workflow interpolated
   `${{ inputs.* }}` — including a caller-settable `test_command` — directly into
   `run:` shell blocks. GitHub Actions does literal text substitution before the
   shell parses the script, so a crafted input could run arbitrary code on the
   Actions runner itself (which holds the repo's `GITHUB_TOKEN`), escaping the
   Docker sandbox the whole design relies on. Fixed by passing every input through
   `env:` instead of template interpolation.

2. **Retrieval fed the patch model hallucination-bait.** The AST call-graph tool's
   "snippet" field returned a location label (`"lines 6-8"`) instead of the actual
   source code at those lines. Since call-graph hits were ranked highest, the patch
   model was drafting fixes against a guess at the code rather than the real file —
   a direct cause of the diff-mechanics failures below.

3. **LLM-generated diffs don't reliably satisfy `git apply` even with correct code.**
   Three distinct, compounding problems, found via a real failing patch and fixed
   with a tested repair pipeline (`app/diff_utils.py`) that anchors every hunk to
   where its content actually occurs in the real file, recomputes header line
   counts, and pads hunks with real context lines:
   - Hunk header line counts (`@@ -a,b +c,d @@`) routinely didn't match the actual
     number of lines in the hunk body.
   - The claimed starting line number was sometimes simply wrong, even when the
     hunk's code content was byte-for-byte correct.
   - Most surprising: **`git apply` can refuse a hunk with zero trailing context
     even when its content and claimed position are both exactly correct**, if a
     similarly-shaped block of code appears later in the same file (confirmed
     against git 2.54 with an isolated, reproducible minimal case — a file with
     `add`/`subtract`/`multiply` functions of identical shape was enough to trigger
     it). Padding each hunk with a couple of real context lines on each side
     resolves the ambiguity. This is covered by a unit test that reproduces the
     exact failure and asserts the repaired diff applies via a real `git apply
     --check`, not a mocked one.

4. **Unauthenticated git push in PR creation.** The local clone used a plain
   `https://` URL with no embedded credentials, so pushing the fix branch failed
   non-interactively. Never caught locally because the PR-creation path wasn't
   exercised against a passing sandbox result until the first real deployed run.

5. **A scratch file got committed into the PR alongside the real fix.** The patch
   was written to a file inside the clone directory before `git add -A`, so the
   scratch patch file itself got committed. Caught by inspecting the actual opened
   PR's file list, not by reasoning about the code.

6. **A transitive dependency conflict broke the eval harness at import time.**
   `ragas` unconditionally imports a module that was removed from the
   `langchain-community` version the rest of the stack depends on. Fixed with a
   minimal `sys.modules` shim rather than downgrading the shared dependency — see
   Tradeoffs below.

7. **Exception handling silently discarded the real cause of failures.** Python's
   `str()` on an `ExceptionGroup` (what `anyio`'s `TaskGroup` raises — used
   internally by the MCP stdio client) returns only a generic summary
   ("unhandled errors in a TaskGroup (1 sub-exception)"); the actual nested
   exception was never logged anywhere, locally or on a deployed service, because
   the orchestrator's own exception handler caught it before the process could
   crash and print a traceback. Fixed by recursively unpacking `.exceptions` so the
   real cause always reaches `state["error"]` (and therefore the dashboard).

8. **A dev/prod backend-parity gap in retrieval.** Local Qdrant permits filtering on
   an unindexed payload field (it just does a full scan); the managed Qdrant Cloud
   instance rejects the same filter with a 400 unless an explicit payload index
   exists. Identical application code behaved differently purely because of a
   backend configuration difference — found only by running against the real
   managed service.

9. **BM25 retrieval had two correctness bugs.** Naive whitespace-only tokenization
   failed to match identifiers immediately followed by punctuation (`helper(x):`
   never matched a query for `helper`). Separately, filtering BM25 hits by
   `score > 0` is unreliable on a small corpus: BM25's IDF term can go negative for
   a common token when only a couple of documents exist, silently discarding every
   result. Fixed tokenization to strip punctuation, and replaced the score
   threshold with a token-overlap requirement.

10. **The AST call-graph traversal had an off-by-one in its hop-count loop,** only
    ever resolving the looked-up symbol itself and never its callers/callees at
    `depth=1` — the loop needed `depth + 1` iterations, not `depth`, since the first
    iteration only resolves the starting symbol.

11. **A failed run discarded its own progress.** The orchestrator's top-level
    exception handler fell back to the pre-run *initial* state rather than the
    latest state the graph actually reached, so a node failing partway through a run
    wiped out whatever triage/retrieval/patch output (and audit trail) had already
    been produced before the failure.

12. **Retrieval had no repo isolation.** `QdrantCodeStore.search()` had no filter on
    the repo-tag payload field, so semantically similar code chunks from a
    *different* indexed repo in the same shared collection could surface in another
    repo's retrieval results — found by noticing unrelated function names in a real
    run's retrieval hits. Fixed with an explicit per-repo filter, verified with an
    isolation test against two distinct repos in the same collection.

13. **The deployed write endpoint had no authentication.** `POST /runs` was reachable
    by anyone who found the URL, who could then spend the deployed owner's LLM and
    GitHub Actions quota and open PRs under their identity — a live exposure on a
    real public deployment, not a hypothetical. Fixed with a shared-secret bearer
    token required on the write endpoint only; read endpoints (run status, the
    dashboard) stay open since there's no login flow and run data isn't sensitive
    here. The frontend's key entry is deliberately never a `NEXT_PUBLIC_*` build-time
    constant, since Next.js inlines those into the public JS bundle — it's entered
    client-side and kept in `localStorage` per browser instead.

14. **An uncaught exception masqueraded as a CORS failure.** A bad or nonexistent
    issue URL raised inside the request/response cycle (resolving it against the
    GitHub API happens synchronously before the background run starts), and the
    resulting unhandled 500 didn't reliably carry CORS headers — the browser reported
    a generic "Failed to fetch" with no usable detail instead of the real error.
    Found by testing the new auth flow against an intentionally-fake repo from an
    actual browser (curl doesn't enforce CORS, so it only ever showed the real 500).
    Fixed by catching the resolution step explicitly and returning a clean 400.

15. **A reasoning gap fixed with a verification step, not just hope.** See the
    `max_of` result above — the patch prompt now requires tracing the patched code
    against the issue's own reproduction before finalizing, instead of pattern-
    matching "this looks like a fix." Re-validated against the exact case that failed
    twice before, not a fresh easier one.

16. **An empty directory passed a local build but broke a fresh clone.**
    `frontend/public/` only ever held an empty subdirectory; git doesn't track empty
    directories, so it existed on my local disk (where the build test ran and
    passed) but was never actually committed. The first real deployment — a fresh
    clone, not a working tree that happened to have the directory already —
    failed at `COPY --from=builder /app/public ./public` with "not found." Fixed
    with a tracked placeholder file, verified against a genuinely fresh clone (not
    the working tree) before trusting it again.

17. **"Deployed" (green, healthy) and completely unreachable were both true at
    once.** After fixing #16, the frontend built and Render reported it deployed —
    but every external request returned 502. The container was healthy from the
    platform's perspective; the platform's proxy simply never reached it. Root
    cause: Next's generated server auto-binds to `process.env.PORT`, which the
    platform injects into the container independently of whatever port its proxy
    actually forwards to — a mismatch that produces exactly this symptom (healthy
    container, unreachable service) rather than a visible crash. Fixed by pinning
    the port inline in the container's command, overriding the platform's injected
    value for that process specifically, and verified locally by deliberately
    injecting a conflicting `PORT` into the container before trusting the fix.

## Tradeoffs (deliberate, not bugs)

- **One LangGraph agent with per-node scoped identity, not a true multi-agent
  architecture.** Each node (`hivefix-triage`, `hivefix-retriever`,
  `hivefix-patcher`, `hivefix-verifier`, `hivefix-publisher`) has an enforced
  allowlist of what it's permitted to do (`ScopedGitHubClient` raises if a node
  calls outside its own scope), with every action and LLM call tagged by identity
  in both a structured audit trail and LangSmith. This gets most of the
  least-privilege benefit of separate agents with a far smaller operational
  surface — one process, one credential set — at the cost of that scoping being
  enforced in application code rather than at an OS or network boundary.

- **Qdrant's semantic-search contribution is a placeholder, not a real signal.**
  Standing up a separate embeddings API was out of scope, so code chunks are
  embedded with a deterministic hashing function rather than a real embedding
  model. BM25 and the AST call-graph carry the actual localization signal; Qdrant
  acts closer to a tie-breaker than a meaningful semantic search. Swapping in a real
  embedding model is a contained, one-file change (`app/vectorstore/qdrant_store.py`)
  when it's needed.

- **Local diff validation before every sandbox dispatch.** `patch_node` runs
  `git apply --check` against the real clone (and the repair pipeline above) before
  ever dispatching a GitHub Actions run, trading a small amount of extra local
  compute per patch attempt for not wasting a full sandbox round-trip on a patch
  that was never going to apply in the first place.

- **A bounded retry count that can end in "unresolved" rather than a guess.**
  The gate will abort a run after exhausting its patch-attempt budget rather than
  opening a PR for an unverified fix — the deliberate cost of that choice is exactly
  the `max_of` result above: a fixable bug the agent didn't resolve within one run,
  in exchange for the 0% false-approval guarantee holding unconditionally.

- **HiveFix's identity on GitHub is textual, not a distinguishable account.**
  The commit itself is correctly attributed (`author: HiveFix
  <hivefix-bot@users.noreply.github.com>`, visible in the commit history), and
  every PR body states "Opened autonomously by HiveFix — no human edits in the
  loop." But opening a PR via the GitHub API is tied to whatever token made the
  call, and that's the repo owner's own fine-grained PAT — so the PR's "opened
  by" badge, avatar, and profile link on GitHub's own UI all show the owner, not
  a separate HiveFix identity. (Verified directly against a real merged PR, not
  assumed from the code.) Fixing this for real needs HiveFix to act through its
  own GitHub identity — a dedicated bot account, or a registered GitHub App (the
  pattern tools like Dependabot use, which shows an "App" badge) — either of
  which needs an account HiveFix's own code can't create for itself. Left as the
  owner's identity for now, a deliberate scope cut rather than an oversight.
