"""Load and validate committed evaluation ground truth."""

from __future__ import annotations

import json
from pathlib import Path

from .config import DATASET_DIR


def load_json(name: str):
    return json.loads((DATASET_DIR / name).read_text(encoding="utf-8"))


def load_conversations():
    return load_json("conversations.json")


def load_rag_ground_truth():
    return load_json("rag_ground_truth.json")


def load_tool_invocations():
    return load_json("tool_invocations.json")


def validate_datasets(repository_root: Path | None = None) -> dict:
    root = repository_root or Path(__file__).resolve().parents[1]
    conversations = load_conversations()
    rag = load_rag_ground_truth()
    tools = load_tool_invocations()
    errors = []

    if len(conversations) < 10:
        errors.append("At least 10 multi-turn conversations are required")
    if any(len(item.get("turns", [])) < 2 for item in conversations):
        errors.append("Every conversation must contain at least two turns")
    if not 20 <= len(rag) <= 30:
        errors.append("RAG ground truth must contain 20–30 retrieval queries")
    if len(rag) < 30:
        errors.append("At least 30 RAG answer pairs are required for faithfulness")

    corpus_sources = {path.name for path in (root / "knowledge_base").glob("*.txt")}
    annotated_sources = {
        source for item in rag for source in item.get("relevant_sources", [])
    }
    missing_sources = sorted(annotated_sources - corpus_sources)
    if missing_sources:
        errors.append(f"Unknown annotated sources: {', '.join(missing_sources)}")

    ids = [item["id"] for collection in (conversations, rag, tools) for item in collection]
    if len(ids) != len(set(ids)):
        errors.append("Dataset IDs must be globally unique")

    return {
        "ok": not errors,
        "errors": errors,
        "counts": {
            "conversations": len(conversations),
            "conversation_turns": sum(len(item["turns"]) for item in conversations),
            "rag_queries": len(rag),
            "tool_prompts": len(tools),
            "corpus_documents": len(corpus_sources),
        },
    }
