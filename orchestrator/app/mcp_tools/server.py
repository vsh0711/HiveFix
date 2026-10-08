"""MCP server exposing BM25 code search and AST call-graph traversal as tools the
LangGraph patch-localization step calls. Indexes are built per-repo-path and cached
for the lifetime of the server process.
"""

from mcp.server.fastmcp import FastMCP

from .ast_callgraph import CallGraph
from .bm25_index import BM25CodeIndex

mcp = FastMCP("hivefix-code-tools")

_bm25_cache: dict[str, BM25CodeIndex] = {}
_callgraph_cache: dict[str, CallGraph] = {}


def _get_bm25(repo_path: str) -> BM25CodeIndex:
    if repo_path not in _bm25_cache:
        _bm25_cache[repo_path] = BM25CodeIndex(repo_path)
    return _bm25_cache[repo_path]


def _get_callgraph(repo_path: str) -> CallGraph:
    if repo_path not in _callgraph_cache:
        _callgraph_cache[repo_path] = CallGraph(repo_path)
    return _callgraph_cache[repo_path]


@mcp.tool()
def bm25_search(repo_path: str, query: str, k: int = 8) -> list[dict]:
    """Search the repo's function/class-level code chunks with BM25 for text relevant
    to the given query (e.g. an error message or issue description fragment)."""
    return _get_bm25(repo_path).search(query, k=k)


@mcp.tool()
def callgraph_lookup(repo_path: str, symbol: str, depth: int = 1) -> list[dict]:
    """Return a function/class's own definition plus its callers and callees up to
    `depth` hops, to localize faults along the call path of a suspected symbol."""
    return _get_callgraph(repo_path).lookup(symbol, depth=depth)


def clear_cache(repo_path: str) -> None:
    _bm25_cache.pop(repo_path, None)
    _callgraph_cache.pop(repo_path, None)


if __name__ == "__main__":
    mcp.run()
