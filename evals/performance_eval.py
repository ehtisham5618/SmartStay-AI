"""Latency, throughput, and concurrency evaluation against a live server."""

from __future__ import annotations

import asyncio
import time
import uuid

from .client import websocket_turn
from .config import EvalConfig
from .metrics import safe_divide, summarize


SCENARIOS = {
    "simple": "Hello! Please briefly introduce SmartStay AI.",
    "rag_only": "What is SmartStay Hotel's cancellation policy?",
    "tool_only": "Calculate the cost of a Deluxe room from 2026-06-01 to 2026-06-04 for two guests.",
    "mixed_rag_tool": "Using the hotel policy, explain cancellation and calculate a Suite from 2026-07-10 to 2026-07-12 for two guests.",
}


def _successful(results: list[dict]) -> list[dict]:
    return [result for result in results if not result.get("error")]


def _latency_summary(results: list[dict]) -> dict:
    successes = _successful(results)
    return {
        "trials": len(results),
        "successful": len(successes),
        "error_rate": 1.0 - safe_divide(len(successes), len(results)),
        "ttft_ms": summarize([item["ttft_ms"] for item in successes if item.get("ttft_ms") is not None]),
        "inter_token_ms": summarize(
            [item["inter_token_ms"] for item in successes if item.get("inter_token_ms") is not None]
        ),
        "end_to_end_ms": summarize([item["e2e_ms"] for item in successes]),
    }


async def evaluate_latency(config: EvalConfig, trials: int | None = None) -> dict:
    trial_count = trials or config.latency_trials
    output = {}
    for scenario, message in SCENARIOS.items():
        results = []
        for index in range(trial_count):
            session_id = f"latency-{scenario}-{index}-{uuid.uuid4().hex[:8]}"
            results.append(
                await websocket_turn(
                    config.ws_url,
                    message,
                    session_id=session_id,
                    timeout=config.request_timeout_seconds,
                )
            )
        output[scenario] = _latency_summary(results)
    return output


async def _simulated_user(config: EvalConfig, level: int, user_index: int) -> list[dict]:
    session_id = f"load-{level}-{user_index}-{uuid.uuid4().hex[:8]}"
    prompts = [
        "Hello, my name is Evaluation Guest.",
        "What time is hotel check-in?",
        "Calculate a Standard room from 2026-08-01 to 2026-08-03 for one guest.",
    ]
    turns = []
    for prompt in prompts:
        turns.append(
            await websocket_turn(
                config.ws_url,
                prompt,
                session_id=session_id,
                timeout=config.request_timeout_seconds,
            )
        )
    return turns


async def evaluate_concurrency(config: EvalConfig, levels: tuple[int, ...] | None = None) -> dict:
    test_levels = levels or config.concurrency_levels
    rows = []
    for level in test_levels:
        started = time.perf_counter()
        batches = await asyncio.gather(*(_simulated_user(config, level, index) for index in range(level)))
        duration = time.perf_counter() - started
        results = [turn for batch in batches for turn in batch]
        summary = _latency_summary(results)
        median_ttft = summary["ttft_ms"].get("median")
        median_e2e = summary["end_to_end_ms"].get("median")
        sustainable = (
            summary["error_rate"] <= 0.05
            and median_ttft is not None
            and median_ttft <= config.acceptable_ttft_ms
            and median_e2e is not None
            and median_e2e <= config.acceptable_e2e_ms
        )
        rows.append(
            {
                "concurrent_users": level,
                "turns": len(results),
                "duration_seconds": duration,
                "turns_per_second": safe_divide(len(results), duration),
                "sustainable": sustainable,
                **summary,
            }
        )

    sustainable_levels = [row["concurrent_users"] for row in rows if row["sustainable"]]
    breakpoint = next((row["concurrent_users"] for row in rows if not row["sustainable"]), None)
    return {
        "thresholds": {
            "maximum_error_rate": 0.05,
            "median_ttft_ms": config.acceptable_ttft_ms,
            "median_end_to_end_ms": config.acceptable_e2e_ms,
        },
        "max_sustainable_concurrent_users": max(sustainable_levels, default=0),
        "breakpoint_concurrent_users": breakpoint,
        "levels": rows,
    }


async def evaluate_performance(
    config: EvalConfig,
    trials: int | None = None,
    levels: tuple[int, ...] | None = None,
) -> dict:
    return {
        "latency": await evaluate_latency(config, trials),
        "concurrency": await evaluate_concurrency(config, levels),
    }
