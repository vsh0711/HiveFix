"""Offline RAGAS evaluation: scores how well each run's patch is grounded in the
retrieved context, over a sampled set of past runs. Run with:

    python -m app.eval.ragas_eval path/to/eval_set.jsonl

Each line of the eval set is a JSON object:
{"question": issue summary, "contexts": [retrieved snippets],
 "answer": patch_diff, "ground_truth": reference patch (optional)}
"""

import json
import sys

from . import _ragas_compat

_ragas_compat.apply()

from datasets import Dataset  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.metrics import context_precision, context_recall, faithfulness  # noqa: E402


def load_eval_set(path: str) -> Dataset:
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return Dataset.from_list(rows)


def run_eval(path: str) -> dict:
    from langchain_groq import ChatGroq

    from ..config import settings
    from ragas.run_config import RunConfig

    dataset = load_eval_set(path)
    judge_llm = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0)

    # answer_relevancy needs real embeddings (compares a synthetic question's
    # embedding to the original) — HiveFix's own embedder is a placeholder hash, not
    # semantically meaningful, so that metric would just be noise. faithfulness,
    # context_precision, and context_recall are LLM-judge metrics instead.
    metrics = [faithfulness, context_precision, context_recall]
    # Groq's free tier rate-limits concurrent requests; ragas's default
    # max_workers=16 fires enough parallel judge calls to trip that, surfacing as
    # TimeoutError (NaN scores) rather than a clear rate-limit error. Serializing
    # avoids it at the cost of eval wall-clock time.
    run_config = RunConfig(max_workers=2, timeout=180)
    result = evaluate(dataset, metrics=metrics, llm=judge_llm, run_config=run_config)
    return result.to_pandas().to_dict(orient="records")


if __name__ == "__main__":
    eval_path = sys.argv[1] if len(sys.argv) > 1 else "eval_set.jsonl"
    scores = run_eval(eval_path)
    print(json.dumps(scores, indent=2))
