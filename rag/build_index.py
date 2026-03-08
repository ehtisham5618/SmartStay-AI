"""Rebuild the local hotel-policy FAISS index."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .chunker import chunk_text
ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "knowledge_base"
DEFAULT_INDEX_DIR = ROOT / "data" / "index"


def collect_chunks(corpus_dir: Path = CORPUS_DIR) -> tuple[list[str], list[dict]]:
    documents = sorted(corpus_dir.glob("*.txt"))
    if not 50 <= len(documents) <= 100:
        raise RuntimeError(f"Expected 50–100 documents, found {len(documents)} in {corpus_dir}")

    chunks, metadata = [], []
    for document in documents:
        for chunk_index, chunk in enumerate(chunk_text(document.read_text(encoding="utf-8"))):
            chunks.append(chunk)
            metadata.append(
                {
                    "source": document.name,
                    "title": document.stem.replace("_", " ").title(),
                    "chunk": chunk_index,
                }
            )
    return chunks, metadata


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    started = time.perf_counter()
    chunks, metadata = collect_chunks()
    logging.info("Embedding %d chunks from 50 hotel documents", len(chunks))
    from .embeddings import embed_documents
    from .vector_store import build_index

    build_index(chunks, embed_documents(chunks), metadata, DEFAULT_INDEX_DIR)
    logging.info("Index saved to %s in %.2f seconds", DEFAULT_INDEX_DIR, time.perf_counter() - started)


if __name__ == "__main__":
    main()
