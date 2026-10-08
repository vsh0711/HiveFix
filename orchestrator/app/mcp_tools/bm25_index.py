"""BM25 search over function/class-level chunks of a Python repo."""

import ast
import os
import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi


@dataclass
class CodeChunk:
    file_path: str
    symbol: str
    start_line: int
    end_line: int
    text: str


def _iter_python_files(repo_path: str):
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "venv", ".venv", "__pycache__")]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def chunk_repo(repo_path: str) -> list[CodeChunk]:
    """Split every .py file into function/class-level chunks; whole file as fallback."""
    chunks: list[CodeChunk] = []
    for path in _iter_python_files(repo_path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                source = fh.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue

        rel_path = os.path.relpath(path, repo_path)
        lines = source.splitlines()
        found_any = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found_any = True
                start = node.lineno - 1
                end = getattr(node, "end_lineno", node.lineno)
                text = "\n".join(lines[start:end])
                chunks.append(
                    CodeChunk(
                        file_path=rel_path,
                        symbol=node.name,
                        start_line=node.lineno,
                        end_line=end,
                        text=text,
                    )
                )
        if not found_any and source.strip():
            chunks.append(
                CodeChunk(
                    file_path=rel_path,
                    symbol="<module>",
                    start_line=1,
                    end_line=len(lines),
                    text=source,
                )
            )
    return chunks


class BM25CodeIndex:
    def __init__(self, repo_path: str):
        self.chunks = chunk_repo(repo_path)
        tokenized = [self._tokenize(c.text) for c in self.chunks]
        self._chunk_tokens = [set(t) for t in tokenized]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t for t in re.split(r"[^a-zA-Z0-9]+", text.lower()) if t]

    def search(self, query: str, k: int = 8) -> list[dict]:
        if self._bm25 is None:
            return []
        query_tokens = set(self._tokenize(query))
        scores = self._bm25.get_scores(list(query_tokens))
        # On tiny/degenerate corpora BM25's IDF term can go negative for very
        # common tokens, so score > 0 isn't a reliable relevance cutoff — only
        # keep chunks that actually share a token with the query.
        candidates = [
            (s, c, chunk_tokens)
            for s, c, chunk_tokens in zip(scores, self.chunks, self._chunk_tokens)
            if query_tokens & chunk_tokens
        ]
        ranked = sorted(candidates, key=lambda sc: sc[0], reverse=True)[:k]
        return [
            {
                "file_path": c.file_path,
                "symbol": c.symbol,
                "score": float(s),
                "snippet": c.text[:1500],
                "source": "bm25",
            }
            for s, c, _ in ranked
        ]
