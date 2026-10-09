"""Qdrant-backed semantic search over repo code chunks — a fallback alongside BM25
and the AST call-graph for retrieval."""

import hashlib

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from ..mcp_tools.bm25_index import chunk_repo


class QdrantCodeStore:
    def __init__(self):
        self._client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        self._embedder = _VoyageOrFallbackEmbedder()
        self._ensure_collection()

    def _ensure_collection(self):
        existing = [c.name for c in self._client.get_collections().collections]
        if settings.qdrant_collection not in existing:
            self._client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=qmodels.VectorParams(size=self._embedder.dim, distance=qmodels.Distance.COSINE),
            )

        # Idempotent regardless of whether the collection already existed — a
        # collection created before this index existed (e.g. an already-running
        # Qdrant Cloud deployment) needs it added too, not just fresh ones. Local
        # Qdrant permits filtering on an unindexed payload field (full scan);
        # Qdrant Cloud enforces an explicit index, rejecting the "repo" filter in
        # search()/index_repo() with a 400 otherwise.
        self._client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="repo",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )

    def index_repo(self, repo_path: str, owner: str, repo: str) -> None:
        repo_tag = f"{owner}/{repo}"
        # Skip re-indexing if this repo was already indexed in this collection.
        existing = self._client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="repo", match=qmodels.MatchValue(value=repo_tag))]
            ),
            limit=1,
        )
        if existing[0]:
            return

        chunks = chunk_repo(repo_path)[:500]
        points = []
        for c in chunks:
            point_id = int(hashlib.sha1(f"{repo_tag}:{c.file_path}:{c.symbol}".encode()).hexdigest()[:16], 16)
            vector = self._embedder.embed(c.text)
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "repo": repo_tag,
                        "file_path": c.file_path,
                        "symbol": c.symbol,
                        "snippet": c.text[:1500],
                    },
                )
            )
        if points:
            self._client.upsert(collection_name=settings.qdrant_collection, points=points)

    def search(self, query: str, owner: str, repo: str, k: int = 6) -> list[dict]:
        repo_tag = f"{owner}/{repo}"
        vector = self._embedder.embed(query)
        response = self._client.query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            limit=k,
            query_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="repo", match=qmodels.MatchValue(value=repo_tag))]
            ),
        )
        return [
            {
                "file_path": r.payload["file_path"],
                "symbol": r.payload.get("symbol"),
                "score": float(r.score),
                "snippet": r.payload.get("snippet", ""),
                "source": "qdrant",
            }
            for r in response.points
        ]


class _VoyageOrFallbackEmbedder:
    """Thin wrapper so swapping embedding providers doesn't touch QdrantCodeStore.
    Uses a deterministic hashing embedding by default so the project runs without an
    extra embeddings API key; swap in a real embedding model for production use."""

    dim = 384

    def embed(self, text: str) -> list[float]:
        import numpy as np

        seed = int(hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        vec = rng.normal(size=self.dim)
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        return vec.tolist()
