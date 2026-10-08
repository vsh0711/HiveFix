import os
import tempfile

from app.mcp_tools.ast_callgraph import CallGraph
from app.mcp_tools.bm25_index import BM25CodeIndex

SAMPLE_REPO = """
def helper(x):
    return x * 2

def main(x):
    return helper(x) + 1
"""


def _write_sample_repo() -> str:
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "sample.py"), "w") as fh:
        fh.write(SAMPLE_REPO)
    return tmp


def test_bm25_finds_relevant_function():
    repo = _write_sample_repo()
    index = BM25CodeIndex(repo)
    hits = index.search("helper function multiplies value", k=5)
    assert any(h["symbol"] == "helper" for h in hits)


def test_callgraph_links_caller_and_callee():
    repo = _write_sample_repo()
    graph = CallGraph(repo)
    hits = graph.lookup("helper", depth=1)
    symbols = {h["symbol"] for h in hits}
    assert "helper" in symbols
    assert "main" in symbols
