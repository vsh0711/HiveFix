import asyncio
import json
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import settings
from ..run_manager import run_manager

app = FastAPI(title="HiveFix Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """Gates write endpoints (starting a run) behind a shared secret. Read endpoints
    stay open — the dashboard has no login flow, and run state/diffs aren't
    sensitive for this project — but starting a run spends real quota (Groq,
    GitHub Actions) and opens real PRs under the deployed owner's identity, so an
    unauthenticated internet-facing deployment must not let anyone trigger that."""
    if not settings.hivefix_api_key:
        return  # local dev: no key configured, auth is a no-op
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not provided or not secrets.compare_digest(provided, settings.hivefix_api_key):
        raise HTTPException(status_code=401, detail="missing or invalid API key")


class StartRunRequest(BaseModel):
    issue_url: str
    test_command: str = "pytest -q"


@app.post("/runs", dependencies=[Depends(require_api_key)])
async def start_run(req: StartRunRequest):
    try:
        run_id = await run_manager.start_run(req.issue_url, req.test_command)
    except Exception as exc:
        # start_run resolves the issue URL against the GitHub API synchronously
        # before returning — a bad URL or nonexistent repo/issue raises here, in
        # the request/response cycle itself (not in the background task). Left
        # uncaught, Starlette's default error response doesn't reliably carry CORS
        # headers, so the browser reports a generic "Failed to fetch" with no
        # usable detail instead of the real 4xx. A client error (bad input) is far
        # more likely here than a server bug, so 400 rather than 500.
        raise HTTPException(status_code=400, detail=f"could not start run: {exc}") from exc
    return {"run_id": run_id}


@app.get("/runs")
async def list_runs():
    return await run_manager.list_runs()


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    state = await run_manager.get_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    return state


@app.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    pubsub, channel = run_manager.subscribe(run_id)
    await pubsub.subscribe(channel)

    async def event_source():
        try:
            current = await run_manager.get_state(run_id)
            if current:
                yield f"data: {json.dumps(current)}\n\n"
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
                if message and message.get("type") == "message":
                    yield f"data: {message['data']}\n\n"
                    payload = json.loads(message["data"])
                    if payload.get("status") in ("resolved", "failed"):
                        break
                else:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(channel)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
