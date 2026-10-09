import asyncio
import json
import tempfile
import uuid

import redis.asyncio as aioredis

from .config import settings
from .github.client import GitHubClient
from .graph.build import hivefix_graph

STAGE_EVENT_CHANNEL = "hivefix:events:{run_id}"
RUN_KEY = "hivefix:run:{run_id}"
RUN_INDEX_KEY = "hivefix:runs"


def _describe_exception(exc: BaseException, _depth: int = 0) -> str:
    """str(exc) on an ExceptionGroup/TaskGroup error (what anyio raises, which the
    MCP stdio client uses internally) gives only a generic summary like 'unhandled
    errors in a TaskGroup (1 sub-exception)' — the real cause is nested inside and
    silently discarded unless unpacked explicitly. This recurses into
    sub-exceptions so state["error"] (shown on the dashboard) always carries the
    actual failure, not just that something failed inside a task group.
    """
    indent = "  " * _depth
    header = f"{indent}{type(exc).__name__}: {exc}"
    sub_excs = getattr(exc, "exceptions", None)
    if not sub_excs:
        return header
    children = "\n".join(_describe_exception(sub, _depth + 1) for sub in sub_excs)
    return f"{header}\n{children}"


class RunManager:
    def __init__(self):
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def start_run(self, issue_url: str, test_command: str = "pytest -q") -> str:
        run_id = uuid.uuid4().hex[:12]
        client = GitHubClient()
        issue_ref = client.parse_issue_url(issue_url)
        base_ref, _ = client.default_branch_sha(issue_ref.owner, issue_ref.repo)

        clone_dir = tempfile.mkdtemp(prefix=f"hivefix-{run_id}-")
        client.clone_repo(issue_ref.owner, issue_ref.repo, clone_dir)

        initial_state = {
            "run_id": run_id,
            "issue_url": issue_url,
            "repo_url": f"https://github.com/{issue_ref.owner}/{issue_ref.repo}",
            "repo_owner": issue_ref.owner,
            "repo_name": issue_ref.repo,
            "issue_title": issue_ref.title,
            "issue_body": issue_ref.body,
            "base_ref": base_ref,
            "clone_path": clone_dir,
            "test_command": test_command,
            "attempt": 0,
            "max_attempts": settings.max_patch_attempts,
            "status": "queued",
        }
        await self._save_state(run_id, initial_state)
        await self._redis.sadd(RUN_INDEX_KEY, run_id)

        asyncio.create_task(self._execute(run_id, initial_state))
        return run_id

    async def _execute(self, run_id: str, state: dict):
        latest_state = state
        try:
            async for event in hivefix_graph.astream(state, stream_mode="values"):
                latest_state = event
                await self._save_state(run_id, event)
                await self._publish(run_id, event)
        except Exception as exc:  # noqa: BLE001 — surface any failure to the dashboard
            # Fall back on the last state the graph actually reached, not the
            # initial pre-run state, so a mid-run failure doesn't discard whatever
            # triage/retrieval/patch progress (and audit_log entries) already
            # happened before the node that raised.
            failed_state = {**latest_state, "status": "failed", "error": _describe_exception(exc)}
            await self._save_state(run_id, failed_state)
            await self._publish(run_id, failed_state)

    async def _save_state(self, run_id: str, state: dict):
        await self._redis.set(RUN_KEY.format(run_id=run_id), json.dumps(state, default=str))

    async def _publish(self, run_id: str, state: dict):
        await self._redis.publish(STAGE_EVENT_CHANNEL.format(run_id=run_id), json.dumps(state, default=str))

    async def get_state(self, run_id: str) -> dict | None:
        raw = await self._redis.get(RUN_KEY.format(run_id=run_id))
        return json.loads(raw) if raw else None

    async def list_runs(self) -> list[dict]:
        run_ids = await self._redis.smembers(RUN_INDEX_KEY)
        states = []
        for run_id in run_ids:
            state = await self.get_state(run_id)
            if state:
                states.append(state)
        return sorted(states, key=lambda s: s.get("run_id", ""), reverse=True)

    def subscribe(self, run_id: str):
        pubsub = self._redis.pubsub()
        return pubsub, STAGE_EVENT_CHANNEL.format(run_id=run_id)


run_manager = RunManager()
