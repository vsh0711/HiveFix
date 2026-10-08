from .. import identity
from ..audit import append_audit, audit_event
from ..mcp_tools.ast_callgraph import CallGraph
from ..mcp_tools.bm25_index import BM25CodeIndex
from ..models.state import RunState
from ..vectorstore.qdrant_store import QdrantCodeStore


def retrieve_node(state: RunState) -> RunState:
    node_identity = identity.RETRIEVE
    repo_path = state["clone_path"]
    sources_used: list[str] = []

    bm25 = BM25CodeIndex(repo_path)
    bm25_hits = bm25.search(state["triage_summary"], k=6)
    if bm25_hits:
        sources_used.append("bm25_search")

    callgraph = CallGraph(repo_path)
    callgraph_hits: list[dict] = []
    for symbol in state.get("suspected_symbols", [])[:5]:
        callgraph_hits.extend(callgraph.lookup(symbol, depth=1))
    if callgraph_hits:
        sources_used.append("callgraph_lookup")

    qdrant_hits: list[dict] = []
    qdrant_error: str | None = None
    try:
        store = QdrantCodeStore()
        store.index_repo(repo_path, state["repo_owner"], state["repo_name"])
        qdrant_hits = store.search(state["triage_summary"], k=6)
        if qdrant_hits:
            sources_used.append("qdrant_search")
    except Exception as exc:  # noqa: BLE001 — Qdrant is a fallback; BM25/call-graph still carry the run
        qdrant_error = str(exc)

    seen: set[tuple[str, str]] = set()
    merged: list[dict] = []
    for hit in bm25_hits + callgraph_hits + qdrant_hits:
        key = (hit["file_path"], hit.get("symbol") or "")
        if key not in seen:
            seen.add(key)
            merged.append(hit)

    entry = audit_event(
        node_identity,
        action="retrieve_context",
        detail={"tools_used": sources_used, "hit_count": len(merged), "qdrant_error": qdrant_error},
        status="ok" if merged else "empty",
    )

    return {**state, "retrieval_hits": merged, "status": "retrieved", "audit_log": append_audit(state, entry)}
