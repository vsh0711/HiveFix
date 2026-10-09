"""Static call-graph builder over a Python repo, for fault-localization traversal."""

import ast
import os
from collections import defaultdict


class CallGraph:
    """Maps fully-qualified function name -> set of callee names it invokes (by raw name,
    unresolved across modules — good enough for same-repo traversal heuristics)."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.callers: dict[str, set[str]] = defaultdict(set)
        self.callees: dict[str, set[str]] = defaultdict(set)
        self.definitions: dict[str, tuple[str, int, int]] = {}  # name -> (file, start, end)
        self._build()

    def _build(self):
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "venv", ".venv", "__pycache__")]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, self.repo_path)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        source = fh.read()
                    tree = ast.parse(source)
                except (SyntaxError, UnicodeDecodeError, OSError):
                    continue
                self._visit_module(tree, rel)

    def _visit_module(self, tree: ast.AST, rel_path: str):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                end = getattr(node, "end_lineno", node.lineno)
                self.definitions[name] = (rel_path, node.lineno, end)
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        callee = self._call_name(inner)
                        if callee:
                            self.callees[name].add(callee)
                            self.callers[callee].add(name)

    @staticmethod
    def _call_name(call_node: ast.Call) -> str | None:
        func = call_node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    def _read_lines(self, rel_path: str, start: int, end: int) -> str:
        try:
            with open(os.path.join(self.repo_path, rel_path), "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
            return "\n".join(lines[start - 1 : end])
        except OSError:
            return ""

    def lookup(self, symbol: str, depth: int = 1) -> list[dict]:
        """Return the symbol's own definition plus callers/callees up to `depth` hops."""
        seen: set[str] = set()
        frontier = {symbol}
        results: list[dict] = []
        # +1 because the first iteration only resolves `symbol` itself; each
        # subsequent iteration resolves one additional hop of callers/callees.
        for _ in range(max(depth, 0) + 1):
            next_frontier: set[str] = set()
            for name in frontier:
                if name in seen:
                    continue
                seen.add(name)
                if name in self.definitions:
                    file_path, start, end = self.definitions[name]
                    results.append(
                        {
                            "file_path": file_path,
                            "symbol": name,
                            "score": 1.0 if name == symbol else 0.5,
                            "snippet": self._read_lines(file_path, start, end),
                            "source": "callgraph",
                        }
                    )
                next_frontier |= self.callers.get(name, set())
                next_frontier |= self.callees.get(name, set())
            frontier = next_frontier - seen
        return results
