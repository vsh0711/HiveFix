import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..run_manager import run_manager

app = FastAPI(title="HiveFix Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartRunRequest(BaseModel):
    issue_url: str
    test_command: str = "pytest -q"


@app.post("/runs")
async def start_run(req: StartRunRequest):
    run_id = await run_manager.start_run(req.issue_url, req.test_command)
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
