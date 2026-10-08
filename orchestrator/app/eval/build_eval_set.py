"""Builds a RAGAS eval_set.jsonl from resolved HiveFix runs stored in Redis.
Usage: python -m app.eval.build_eval_set > eval_set.jsonl
"""

import asyncio
import json

from ..run_manager import run_manager


async def build() -> list[dict]:
    runs = await run_manager.list_runs()
    rows = []
    for run in runs:
        if run.get("status") != "resolved":
            continue
        rows.append(
            {
                "question": run.get("triage_summary", ""),
                "contexts": [h["snippet"] for h in run.get("retrieval_hits", [])],
                "answer": run.get("patch_diff", ""),
            }
        )
    return rows


if __name__ == "__main__":
    for row in asyncio.run(build()):
        print(json.dumps(row))
