"""Cached asynchronous-friendly retrieval facade."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Callable, List, Optional


class RAGRetriever:
    RETRIEVAL_TERMS = {
        "policy", "policies", "check-in", "check in", "check-out", "check out",
        "room type", "amenity", "amenities", "pool", "gym", "wifi", "wi-fi",
        "breakfast", "restaurant", "parking", "pet", "smoking", "visitor",
        "refund", "cancel", "laundry", "housekeeping", "payment", "meeting",
        "spa", "dietary", "meal", "airport", "accessible", "attraction",
        "tax", "deposit", "no-show", "no show", "group booking", "room service",
        "business center", "hotel location", "directions", "security", "safety",
    }

    def __init__(
        self,
        index_dir: Optional[Path] = None,
        embed_query: Optional[Callable] = None,
        search: Optional[Callable] = None,
        cache_size: int = 128,
    ):
        self.index_dir = index_dir
        self._embed_query = embed_query
        self._search = search
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple, List[dict]] = OrderedDict()
        self._lock = RLock()

    @classmethod
    def should_retrieve(cls, query: str) -> bool:
        normalized = " ".join(query.lower().split())
        return any(term in normalized for term in cls.RETRIEVAL_TERMS)

    def _ensure_dependencies(self) -> None:
        if self._embed_query is None:
            from .embeddings import embed_query

            self._embed_query = embed_query
        if self._search is None:
            from . import vector_store

            if not vector_store.is_ready() and not vector_store.load_index(self.index_dir or vector_store.DEFAULT_INDEX_DIR):
                raise RuntimeError("RAG index is missing; run python -m rag.build_index")
            self._search = vector_store.search

    def retrieve(self, query: str, top_k: int = 3) -> List[dict]:
        normalized = " ".join(query.lower().split())
        if not normalized:
            return []
        top_k = max(3, min(top_k, 5))
        key = (normalized, top_k)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return [item.copy() for item in self._cache[key]]

        self._ensure_dependencies()
        results = self._search(self._embed_query(query), top_k=top_k)
        with self._lock:
            self._cache[key] = [item.copy() for item in results]
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return results

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
