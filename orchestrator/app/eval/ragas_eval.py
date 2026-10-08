"""Offline RAGAS evaluation: scores how well each run's patch is grounded in the
retrieved context, over a sampled set of past runs. Run with:

    python -m app.eval.ragas_eval path/to/eval_set.jsonl

Each line of the eval set is a JSON object:
{"question": issue summary, "contexts": [retrieved snippets],
 "answer": patch_diff, "ground_truth": reference patch (optional)}
"""

import json
import sys

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness


def load_eval_set(path: str) -> Dataset:
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return Dataset.from_list(rows)


def run_eval(path: str) -> dict:
    dataset = load_eval_set(path)
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    result = evaluate(dataset, metrics=metrics)
    return result.to_pandas().to_dict(orient="records")


if __name__ == "__main__":
    eval_path = sys.argv[1] if len(sys.argv) > 1 else "eval_set.jsonl"
    scores = run_eval(eval_path)
    print(json.dumps(scores, indent=2))
