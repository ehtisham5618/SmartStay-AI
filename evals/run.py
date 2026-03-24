"""Command-line entry point for the SmartStay AI evaluation suite."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from pathlib import Path

from .client import server_is_ready
from .config import EvalConfig
from .conversation_eval import evaluate_conversations
from .datasets import validate_datasets
from .performance_eval import evaluate_performance
from .rag_eval import evaluate_rag
from .report import environment_metadata, write_reports
from .tool_eval import evaluate_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate SmartStay AI correctness and performance")
    parser.add_argument("--mode", choices=("all", "correctness", "performance", "validate"), default="all")
    parser.add_argument("--quick", action="store_true", help="Run a short smoke evaluation")
    parser.add_argument("--network-tools", action="store_true", help="Include the live weather API check")
    parser.add_argument("--base-url")
    parser.add_argument("--ws-url")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--trials", type=int, help="Override latency trials per scenario")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> tuple[dict, dict]:
    config = EvalConfig()
    config = replace(
        config,
        base_url=args.base_url or config.base_url,
        ws_url=args.ws_url or config.ws_url,
        output_dir=args.output_dir or config.output_dir,
    )
    report = {
        "suite": "SmartStay AI comprehensive evaluation",
        "mode": args.mode,
        "quick": args.quick,
        "environment": environment_metadata(),
        "datasets": validate_datasets(),
        "correctness": {},
        "performance": {},
        "failures": [],
    }

    if args.mode in {"all", "correctness", "validate"}:
        report["correctness"]["tools"] = await evaluate_tools(args.network_tools)

    requires_server = args.mode in {"all", "correctness", "performance"}
    ready, readiness_error = await server_is_ready(config.base_url) if requires_server else (False, "")
    if requires_server and not ready:
        report["failures"].append(
            f"SmartStay API was not reachable at {config.base_url}; live checks were skipped ({readiness_error})."
        )
    elif ready:
        if args.mode in {"all", "correctness"}:
            report["correctness"]["conversation"] = await evaluate_conversations(
                config.ws_url,
                timeout=config.request_timeout_seconds,
                limit=2 if args.quick else None,
            )
            report["correctness"]["rag"] = await evaluate_rag(
                config.base_url,
                config.ws_url,
                timeout=config.request_timeout_seconds,
                limit=3 if args.quick else None,
            )
        if args.mode in {"all", "performance"}:
            trials = args.trials or (2 if args.quick else config.latency_trials)
            levels = (1, 2) if args.quick else config.concurrency_levels
            report["performance"] = await evaluate_performance(config, trials=trials, levels=levels)

    artifacts = write_reports(report, config.output_dir)
    return report, artifacts


def main() -> int:
    args = parse_args()
    report, artifacts = asyncio.run(run(args))
    print(f"Evaluation complete with {len(report['failures'])} runner-level failure(s).")
    for name, path in artifacts.items():
        print(f"{name}: {path}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
