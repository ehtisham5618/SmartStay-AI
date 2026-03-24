"""Benchmark warm RAG and tool preprocessing without LLM generation."""

from __future__ import annotations

import asyncio
import json
import statistics
import time

from rag.retriever import RAGRetriever
from tools.orchestrator import ToolOrchestrator


QUERIES = [
    "What is the cancellation policy?",
    "Is parking available?",
    "When is check-out?",
    "Can I bring a pet?",
    "What time does breakfast start?",
]


async def timed_preprocessing(retriever, orchestrator, query, user_id):
    started = time.perf_counter()
    rag, tools = await asyncio.gather(
        asyncio.to_thread(retriever.retrieve, query, 3),
        orchestrator.execute_for_message(query, user_id),
    )
    return {
        "query": query,
        "latency_ms": (time.perf_counter() - started) * 1_000,
        "sources": [item["source"] for item in rag],
        "tools": [result.as_dict() for result in tools],
    }


async def main():
    retriever = RAGRetriever()
    orchestrator = ToolOrchestrator()
    await asyncio.to_thread(retriever.retrieve, "warm hotel retrieval", 3)
    results = []
    for index, query in enumerate(QUERIES):
        results.append(await timed_preprocessing(retriever, orchestrator, query, f"bench-{index}"))

    concurrent = await asyncio.gather(
        timed_preprocessing(retriever, orchestrator, "Price a Suite from 2026-05-01 to 2026-05-03", "user-a"),
        timed_preprocessing(retriever, orchestrator, "Remember my name is Sara", "user-b"),
    )
    values = [result["latency_ms"] for result in results]
    report = {
        "runs": results,
        "two_user_concurrent": concurrent,
        "summary": {
            "average_ms": statistics.mean(values),
            "median_ms": statistics.median(values),
            "maximum_ms": max(values),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

