# Technical findings

Real results, real bugs, and the deliberate tradeoffs behind HiveFix — gathered by
actually running the system against a live demo repo
([vsh0711/hivefix-demo-calc](https://github.com/vsh0711/hivefix-demo-calc)) and a
real deployment, not from code review alone.

## Quantitative results

Six distinct, deliberately-planted single-line bugs were run through the full
pipeline end-to-end (real LLM, real MCP tool-calling retrieval, real GitHub Actions
sandbox, real PR):

| Issue | Bug type | Result |
|---|---|---|
| `subtract()` uses `+` instead of `-` | wrong operator | **resolved** |
| `is_positive(0)` returns `True` | boundary/comparison | **resolved** |
| `factorial(5)` returns `24` not `120` | off-by-one loop | **resolved** |
| `divide(7, 2)` returns `3` not `3.5` | wrong operator (`//` vs `/`) | **resolved** |
| `max_of(3, 9)` returns `3` not `9` | inverted comparison branches | **not resolved** |
| `remainder(7, 2)` returns `3` not `1` | wrong operator (`//` vs `%`) | **resolved** |

**5/6 (83%) resolved**, each with a minimal, correct, exactly-one-line diff — no
extraneous changes in any merged PR. **0% false-approval rate held across every
attempt on every issue**: no incorrect patch was ever merged, because the sandboxed
test gate rejected every wrong patch before a PR could open, including both attempts
on the one unresolved issue.

The `max_of` failure is itself a useful result, not a blank: on both attempts the
patch confidently restructured the `if` branch to `return a` in both paths — a
different wrong answer each time, read as a plausible fix by the rationale text, but
never correct. The gate caught it both times and the run correctly stopped after its
retry budget rather than publishing a guess. This is the system working as designed:
a sandboxed, bounded-retry gate exists specifically to make wrong patches cheap to
catch and impossible to accidentally ship.

Caveat: six single-line synthetic bugs in one small file is enough to validate the
pipeline and produce an honest number, not enough to claim a general resolve rate —
see [eval_results.md](eval_results.md) for the same caveat applied to the RAGAS
numbers, and `docs/eval_results.md`'s note on what a representative-scale eval (e.g.
SWE-bench-style sampling) would take.

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
