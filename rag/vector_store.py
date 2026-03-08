"""Persisted FAISS cosine index with source metadata."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List

import numpy as np


DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "index"
_index = None
_chunks: List[str] = []
_metadata: List[Dict[str, Any]] = []
_lock = RLock()


def _faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError("Install faiss-cpu to use local retrieval") from exc
    return faiss


def build_index(chunks: List[str], embeddings, metadata: List[Dict[str, Any]], index_dir: Path = DEFAULT_INDEX_DIR) -> None:
    global _index, _chunks, _metadata
    if not chunks or len(chunks) != len(metadata) or len(chunks) != len(embeddings):
        raise ValueError("Chunks, embeddings, and metadata must have equal non-zero lengths")

    matrix = np.asarray(embeddings, dtype="float32")
    faiss = _faiss()
    faiss.normalize_L2(matrix)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "faiss.index"))
    (index_dir / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    (index_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    with _lock:
        _index, _chunks, _metadata = index, list(chunks), list(metadata)


def load_index(index_dir: Path = DEFAULT_INDEX_DIR) -> bool:
    global _index, _chunks, _metadata
    paths = [index_dir / "faiss.index", index_dir / "chunks.json", index_dir / "metadata.json"]
    if not all(path.is_file() for path in paths):
        return False
    with _lock:
        _index = _faiss().read_index(str(paths[0]))
        _chunks = json.loads(paths[1].read_text(encoding="utf-8"))
        _metadata = json.loads(paths[2].read_text(encoding="utf-8"))
    return True


def is_ready() -> bool:
    return _index is not None and bool(_chunks)


def search(query_embedding, top_k: int = 3) -> List[dict]:
    if not is_ready():
        raise RuntimeError("RAG index is not built; run python -m rag.build_index")
    vector = np.asarray(query_embedding, dtype="float32").reshape(1, -1)
    _faiss().normalize_L2(vector)
    scores, indices = _index.search(vector, min(max(top_k, 3), len(_chunks)))
    results = []
    for score, index in zip(scores[0], indices[0]):
        if index < 0:
            continue
        results.append({"text": _chunks[index], "score": float(score), **_metadata[index]})
    return results

