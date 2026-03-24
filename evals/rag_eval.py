"""Retrieval relevance, answer coverage, citation, and lexical faithfulness."""

from __future__ import annotations

import re
import uuid

from .client import http_json, websocket_turn
from .datasets import load_rag_ground_truth
from .metrics import precision_at_k, recall_at_k, reciprocal_rank, safe_divide


STOP_WORDS = {
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "to", "of",
    "in", "on", "for", "with", "that", "this", "it", "you", "your", "our",
    "can", "may", "will", "be", "as", "at", "from", "by", "if", "we", "i",
}


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in STOP_WORDS
    }


def lexical_faithfulness(answer: str, contexts: list[str]) -> float:
    context_tokens = _tokens(" ".join(contexts))
    claims = [sentence for sentence in re.split(r"(?<=[.!?])\s+", answer) if len(_tokens(sentence)) >= 3]
    if not claims:
        return 0.0
    supported = 0
    for claim in claims:
        claim_tokens = _tokens(claim)
        overlap = safe_divide(len(claim_tokens & context_tokens), len(claim_tokens))
        supported += overlap >= 0.45
    return safe_divide(supported, len(claims))


async def evaluate_rag(base_url: str, ws_url: str, timeout: float = 120, limit: int | None = None) -> dict:
    cases = load_rag_ground_truth()[:limit]
    details = []
    for case in cases:
        retrieval = await http_json(
            "POST",
            f"{base_url.rstrip('/')}/api/retrieve",
            {"query": case["query"], "top_k": 3},
            timeout=timeout,
        )
        retrieved = retrieval.get("results", [])
        sources = [item.get("source") for item in retrieved]
        relevant = set(case["relevant_sources"])
        turn = await websocket_turn(
            ws_url,
            case["query"],
            session_id=f"eval-rag-{uuid.uuid4()}",
            timeout=timeout,
        )
        response_lower = turn["response"].lower()
        answer_coverage = safe_divide(
            sum(term.lower() in response_lower for term in case.get("answer_terms", [])),
            len(case.get("answer_terms", [])),
        )
        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "retrieved_sources": sources,
                "relevant_sources": sorted(relevant),
                "precision_at_3": precision_at_k(sources, relevant, 3),
                "recall_at_3": recall_at_k(sources, relevant, 3),
                "mrr": reciprocal_rank(sources, relevant),
                "context_relevance": precision_at_k(sources, relevant, 3),
                "faithfulness": lexical_faithfulness(
                    turn["response"], [item.get("text", "") for item in retrieved]
                ),
                "answer_term_coverage": answer_coverage,
                "citation_present": any(source and f"[{source.lower()}]" in response_lower for source in relevant),
                "retrieval_ms": retrieval.get("latency_ms", 0),
                "error": turn["error"],
            }
        )

    def average(key):
        return safe_divide(sum(item[key] for item in details), len(details))

    return {
        "queries": len(details),
        "precision_at_3": average("precision_at_3"),
        "recall_at_3": average("recall_at_3"),
        "mrr": average("mrr"),
        "context_relevance": average("context_relevance"),
        "faithfulness": average("faithfulness"),
        "answer_term_coverage": average("answer_term_coverage"),
        "citation_rate": average("citation_present"),
        "details": details,
        "faithfulness_method": "Claim-level lexical support: a claim passes when >=45% of content tokens occur in retrieved context",
    }
