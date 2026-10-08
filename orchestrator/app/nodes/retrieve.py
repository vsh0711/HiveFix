import json

from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .. import identity
from ..audit import append_audit, audit_event
from ..config import settings
from ..mcp_tools.mcp_client import build_langchain_tools, mcp_session
from ..models.state import RunState
from ..vectorstore.qdrant_store import QdrantCodeStore

_SYSTEM = """You localize the code responsible for a bug before anyone drafts a fix.
You have two tools, served over MCP by the repo's own code-tools server:
- bm25_search(query, k): lexical search over function/class-level code chunks
- callgraph_lookup(symbol, depth): a suspected symbol's definition plus its callers/callees

Use them to investigate the issue summary and suspected symbols below. Call tools as
many times as useful (each call narrows or confirms a hypothesis), then — once you
have enough to localize the fault — respond with a short plain-text confirmation and
make no further tool calls."""

_MAX_TOOL_ITERATIONS = 4


async def retrieve_node(state: RunState) -> RunState:
    node_identity = identity.RETRIEVE
    repo_path = state["clone_path"]

    tool_calls_made: list[dict] = []
    hits: list[dict] = []

    async with mcp_session() as session:
        tools = build_langchain_tools(session, repo_path)
        tools_by_name = {t.name: t for t in tools}

        llm = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0).bind_tools(tools)

        messages = [
            SystemMessage(content=_SYSTEM),
            HumanMessage(
                content=(
                    f"Issue summary: {state['triage_summary']}\n"
                    f"Suspected symbols: {state.get('suspected_symbols', [])}"
                )
            ),
        ]

        for _ in range(_MAX_TOOL_ITERATIONS):
            response: AIMessage = await llm.ainvoke(
                messages,
                config={
                    "tags": [node_identity.name],
                    "run_name": node_identity.name,
                    "metadata": {"run_id": state["run_id"], "node": node_identity.name},
                },
            )
            messages.append(response)

            if not response.tool_calls:
                break

            for call in response.tool_calls:
                tool = tools_by_name[call["name"]]
                result = await tool.coroutine(**call["args"])
                hits.extend(result)
                tool_calls_made.append({"name": call["name"], "args": call["args"], "result_count": len(result)})
                messages.append(
                    ToolMessage(content=json.dumps(result), tool_call_id=call["id"])
                )

    qdrant_hits: list[dict] = []
    qdrant_error: str | None = None
    try:
        store = QdrantCodeStore()
        store.index_repo(repo_path, state["repo_owner"], state["repo_name"])
        qdrant_hits = store.search(state["triage_summary"], state["repo_owner"], state["repo_name"], k=6)
    except Exception as exc:  # noqa: BLE001 — Qdrant is a fallback; MCP tool hits still carry the run
        qdrant_error = str(exc)

    seen: set[tuple[str, str]] = set()
    merged: list[dict] = []
    for hit in hits + qdrant_hits:
        key = (hit["file_path"], hit.get("symbol") or "")
        if key not in seen:
            seen.add(key)
            merged.append(hit)

    entry = audit_event(
        node_identity,
        action="retrieve_context",
        detail={"mcp_tool_calls": tool_calls_made, "hit_count": len(merged), "qdrant_error": qdrant_error},
        status="ok" if merged else "empty",
    )

    return {**state, "retrieval_hits": merged, "status": "retrieved", "audit_log": append_audit(state, entry)}
