"""Environment-driven evaluation configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalConfig:
    base_url: str = os.getenv("SMARTSTAY_BASE_URL", "http://localhost:8000")
    ws_url: str = os.getenv("SMARTSTAY_WS_URL", "ws://localhost:8000/ws/chat")
    output_dir: Path = Path(os.getenv("SMARTSTAY_EVAL_OUTPUT", "eval_reports"))
    latency_trials: int = int(os.getenv("SMARTSTAY_LATENCY_TRIALS", "30"))
    concurrency_levels: tuple[int, ...] = tuple(
        int(value) for value in os.getenv("SMARTSTAY_CONCURRENCY", "1,2,4,6,8").split(",")
    )
    acceptable_ttft_ms: float = float(os.getenv("SMARTSTAY_MAX_TTFT_MS", "2000"))
    acceptable_e2e_ms: float = float(os.getenv("SMARTSTAY_MAX_E2E_MS", "10000"))
    request_timeout_seconds: float = float(os.getenv("SMARTSTAY_EVAL_TIMEOUT", "120"))


DATASET_DIR = Path(__file__).resolve().parent / "datasets"
