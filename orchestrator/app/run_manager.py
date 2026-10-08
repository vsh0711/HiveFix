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
        try:
            async for event in hivefix_graph.astream(state, stream_mode="values"):
                await self._save_state(run_id, event)
                await self._publish(run_id, event)
        except Exception as exc:  # noqa: BLE001 — surface any failure to the dashboard
            failed_state = {**state, "status": "failed", "error": str(exc)}
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
