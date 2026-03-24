"""Rule-based evaluation of committed multi-turn dialogue rubrics."""

from __future__ import annotations

import uuid

from .client import websocket_turn
from .datasets import load_conversations
from .metrics import safe_divide


def _contains_any(response: str, terms: list[str]) -> bool:
    lower = response.lower()
    return not terms or any(term.lower() in lower for term in terms)


async def evaluate_conversations(ws_url: str, timeout: float = 120, limit: int | None = None) -> dict:
    dialogues = load_conversations()[:limit]
    results = []

    for dialogue in dialogues:
        session_id = f"eval-conversation-{uuid.uuid4()}"
        user_id = f"eval-user-{uuid.uuid4()}"
        turn_results = []
        responses = []
        for turn in dialogue["turns"]:
            observed = await websocket_turn(
                ws_url,
                turn["message"],
                session_id=session_id,
                user_id=user_id,
                timeout=timeout,
            )
            responses.append(observed["response"])
            expected = turn["expect"]
            tool_names = {item.get("name") for item in observed["context"].get("tools", [])}
            source_names = {item.get("source") for item in observed["context"].get("sources", [])}
            content_ok = _contains_any(observed["response"], expected.get("contains_any", []))
            refusal_ok = not expected.get("refusal") or "hotel-related" in observed["response"].lower()
            tool_ok = not expected.get("tool") or expected["tool"] in tool_names
            source_ok = not expected.get("source") or expected["source"] in source_names
            task_ok = not observed["error"] and content_ok and refusal_ok and tool_ok and source_ok
            policy_ok = (
                "hotel-related" in observed["response"].lower()
                if expected.get("refusal")
                else "hotel-related" not in observed["response"].lower()
            )
            turn_results.append(
                {
                    "message": turn["message"],
                    "response": observed["response"],
                    "task_ok": task_ok,
                    "policy_ok": policy_ok,
                    "tool_ok": tool_ok,
                    "source_ok": source_ok,
                    "error": observed["error"],
                }
            )

        later_text = " ".join(responses[1:]).lower()
        memory_terms = dialogue.get("memory_terms", [])
        coherence = safe_divide(
            sum(term.lower() in later_text for term in memory_terms),
            len(memory_terms),
        ) if memory_terms else 1.0
        results.append(
            {
                "id": dialogue["id"],
                "title": dialogue["title"],
                "task_completed": all(turn["task_ok"] for turn in turn_results),
                "policy_adherence": safe_divide(sum(turn["policy_ok"] for turn in turn_results), len(turn_results)),
                "coherence": coherence,
                "turns": turn_results,
            }
        )

    return {
        "dialogues": len(results),
        "task_completion_rate": safe_divide(sum(item["task_completed"] for item in results), len(results)),
        "policy_adherence_rate": safe_divide(
            sum(item["policy_adherence"] for item in results), len(results)
        ),
        "mean_coherence": safe_divide(sum(item["coherence"] for item in results), len(results)),
        "results": results,
        "method": "Deterministic rubric checks over responses, source events, tool events, and remembered terms",
    }
