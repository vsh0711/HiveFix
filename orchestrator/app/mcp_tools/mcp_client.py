"""Spawns the HiveFix code-tools MCP server as a subprocess over stdio and exposes
its tools (bm25_search, callgraph_lookup) as LangChain-bindable StructuredTools, so
retrieval is genuine LLM-directed MCP tool-calling rather than a fixed pipeline."""

import json
import sys
from contextlib import asynccontextmanager

from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _parse_result(result) -> list[dict]:
    """MCPServer serializes each item of a `list[dict]` tool return as its own
    TextContent block of JSON; reassemble them into a plain list of dicts."""
    items = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            items.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return items


@asynccontextmanager
async def mcp_session():
    params = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_tools.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def build_langchain_tools(session: ClientSession, repo_path: str) -> list[StructuredTool]:
    """Binds the MCP server's tools to a fixed repo_path (the agent shouldn't be
    choosing which repo to search — only what to search for) and wraps each as a
    LangChain tool an LLM can call directly."""

    async def _bm25_search(query: str, k: int = 8) -> list[dict]:
        result = await session.call_tool("bm25_search", {"repo_path": repo_path, "query": query, "k": k})
        return _parse_result(result)

    async def _callgraph_lookup(symbol: str, depth: int = 1) -> list[dict]:
        result = await session.call_tool("callgraph_lookup", {"repo_path": repo_path, "symbol": symbol, "depth": depth})
        return _parse_result(result)

    return [
        StructuredTool.from_function(
            coroutine=_bm25_search,
            name="bm25_search",
            description=(
                "Search the repo's function/class-level code chunks with BM25 for text "
                "relevant to a query (e.g. an error message or part of the issue description)."
            ),
        ),
        StructuredTool.from_function(
            coroutine=_callgraph_lookup,
            name="callgraph_lookup",
            description=(
                "Return a function/class's own definition plus its callers and callees up "
                "to `depth` hops, to localize a fault along the call path of a suspected symbol."
            ),
        ),
    ]
