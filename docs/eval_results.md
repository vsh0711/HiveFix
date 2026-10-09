# RAGAS eval results

Run against 3 real, distinct bugs resolved end-to-end by HiveFix on a live demo repo
([vsh0711/hivefix-demo-calc](https://github.com/vsh0711/hivefix-demo-calc)) — not
mocked data. Each row's `reference` is the actual correct one-line fix, known because
these were deliberately planted bugs.

| Issue | faithfulness | context_precision | context_recall |
|---|---|---|---|
| [#1](https://github.com/vsh0711/hivefix-demo-calc/issues/1) subtract() adds instead of subtracting | 0.0 | 1.0 | 0.43 |
| [#4](https://github.com/vsh0711/hivefix-demo-calc/issues/4) is_positive(0) returns True | 0.0 | 1.0 | 0.43 |
| [#5](https://github.com/vsh0711/hivefix-demo-calc/issues/5) factorial(5) off-by-one | 0.4 | 1.0 | 1.0 |

Reproduce: `orchestrator/eval_set.jsonl` has the raw rows;
`python -m app.eval.ragas_eval eval_set.jsonl` re-runs it (needs `GROQ_API_KEY` in
the environment — ragas's judge calls go through the same Groq model HiveFix itself
uses).

## Reading these numbers

**`context_precision` ≈ 1.0 across all three** — the retrieved context (BM25 +
call-graph + Qdrant hits) is consistently relevant to the question. This is the
strongest, most trustworthy signal here: retrieval is doing its job.

**`context_recall` is 0.43 for two of three, 1.0 for the third** — measures how much
of the *reference* fix's content is covered by what was retrieved. The two lower
scores correspond to runs where retrieval also pulled in unrelated sibling functions
(`add`, `multiply`) alongside the directly relevant one — not wrong (some
surrounding-code context is useful), but it dilutes this specific metric. Worth
revisiting if `context_recall` matters more than precision for future work: tighter
`k` on the BM25/Qdrant calls, or depth-limiting the call-graph lookup, would likely
raise it.

**`faithfulness` is low (0.0, 0.0, 0.4) despite all three patches being objectively
correct** — each one passed a real sandboxed test run and was merged. This is a
genuine metric-fit problem, not a quality problem: RAGAS's faithfulness metric
extracts discrete natural-language "claims" from the answer via an LLM, then checks
each claim against the context. A unified diff isn't phrased as verifiable
natural-language claims — the claim-extraction step produces awkward fragments that
don't match the context's phrasing, driving the score down regardless of actual
correctness. **Don't read faithfulness as a quality signal for code-diff outputs on
this pipeline** — it's measuring the wrong thing. A metric that would actually fit
here (not implemented) is something closer to "does the diff's changed line map to a
retrieved context snippet" — essentially a code-aware variant of faithfulness that
doesn't yet exist in RAGAS's metric set.

## Sample size caveat

Three issues is enough to validate the harness and surface the faithfulness-metric
mismatch above, not enough to claim a general resolve-rate or quality number. The
original project pitch cited a 31% resolve rate over 240 sampled issues — getting a
real number at that scale would need a much larger, more realistic issue sample
(ideally from real open-source repos, not hand-planted single-line bugs in a throwaway
demo repo) and is the natural next step if this harness needs to produce a headline
metric.
