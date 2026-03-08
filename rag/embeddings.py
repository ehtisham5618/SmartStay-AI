"""Lazy local sentence-transformer embeddings."""

from __future__ import annotations

import os
import threading
from typing import Iterable


MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_model = None
_load_lock = threading.Lock()


def get_model():
    global _model
    if _model is not None:
        return _model
    with _load_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


def embed_documents(texts: Iterable[str]):
    values = list(texts)
    if not values:
        raise ValueError("At least one document chunk is required")
    return get_model().encode(
        values,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )


def embed_query(text: str):
    if not text.strip():
        raise ValueError("Query cannot be empty")
    return get_model().encode(
        [text],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]

