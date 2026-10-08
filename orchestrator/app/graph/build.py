from langgraph.graph import END, StateGraph

from ..models.state import RunState
from ..nodes.open_pr import fail_node, open_pr_node
from ..nodes.patch import patch_node
from ..nodes.retrieve import retrieve_node
from ..nodes.sandbox import sandbox_node
from ..nodes.triage import triage_node


def _gate(state: RunState) -> str:
    result = state.get("sandbox_result") or {}
    if result.get("passed"):
        return "open_pr"
    if state.get("attempt", 0) < state.get("max_attempts", 2):
        return "retry"
    return "fail"


def build_graph():
    graph = StateGraph(RunState)

    graph.add_node("triage", triage_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("patch", patch_node)
    graph.add_node("sandbox", sandbox_node)
    graph.add_node("open_pr", open_pr_node)
    graph.add_node("fail", fail_node)

    graph.set_entry_point("triage")
    graph.add_edge("triage", "retrieve")
    graph.add_edge("retrieve", "patch")
    graph.add_edge("patch", "sandbox")
    graph.add_conditional_edges(
        "sandbox",
        _gate,
        {"open_pr": "open_pr", "retry": "patch", "fail": "fail"},
    )
    graph.add_edge("open_pr", END)
    graph.add_edge("fail", END)

    return graph.compile()


hivefix_graph = build_graph()
