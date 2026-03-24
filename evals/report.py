"""Machine-readable and human-readable evaluation report generation."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path


def environment_metadata() -> dict:
    packages = {}
    for name in ("fastapi", "uvicorn", "websockets", "sentence-transformers", "faiss-cpu", "psutil"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    memory_gb = None
    try:
        import psutil

        memory_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    except ImportError:
        pass
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        "logical_cpu_count": os.cpu_count(),
        "memory_gb": memory_gb,
        "dependencies": packages,
    }


def _percent(value) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def _number(value, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.2f}{suffix}"


def _latency_table(latency: dict) -> list[str]:
    lines = [
        "| Scenario | Trials | Errors | Mean TTFT | Median TTFT | p90 E2E | p99 E2E |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, data in latency.items():
        lines.append(
            f"| {name} | {data['trials']} | {_percent(data['error_rate'])} | "
            f"{_number(data['ttft_ms'].get('mean'), ' ms')} | {_number(data['ttft_ms'].get('median'), ' ms')} | "
            f"{_number(data['end_to_end_ms'].get('p90'), ' ms')} | {_number(data['end_to_end_ms'].get('p99'), ' ms')} |"
        )
    return lines


def _concurrency_table(concurrency: dict) -> list[str]:
    lines = [
        "| Users | Turns/s | Error rate | Median TTFT | Median E2E | Sustainable |",
        "|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in concurrency.get("levels", []):
        lines.append(
            f"| {row['concurrent_users']} | {_number(row['turns_per_second'])} | {_percent(row['error_rate'])} | "
            f"{_number(row['ttft_ms'].get('median'), ' ms')} | "
            f"{_number(row['end_to_end_ms'].get('median'), ' ms')} | {'Yes' if row['sustainable'] else 'No'} |"
        )
    return lines


def build_markdown(report: dict) -> str:
    dataset_validation = report.get("datasets", {})
    datasets = dataset_validation.get("counts", {})
    correctness = report.get("correctness", {})
    dialogue = correctness.get("conversation", {})
    rag = correctness.get("rag", {})
    tools = correctness.get("tools", {})
    functional = tools.get("functional", {})
    routing = tools.get("routing", {})
    performance = report.get("performance", {})
    env = report["environment"]
    lines = [
        "# SmartStay AI Evaluation Report",
        "",
        f"Generated: `{env['generated_at_utc']}`",
        "",
        "## Executive summary",
        "",
        f"- Dialogue task completion: {_percent(dialogue.get('task_completion_rate'))}",
        f"- Policy adherence: {_percent(dialogue.get('policy_adherence_rate'))}",
        f"- Multi-turn coherence: {_percent(dialogue.get('mean_coherence'))}",
        f"- RAG precision@3: {_number(rag.get('precision_at_3'))}",
        f"- RAG recall@3: {_number(rag.get('recall_at_3'))}",
        f"- RAG MRR: {_number(rag.get('mrr'))}",
        f"- Tool functional pass rate: {_percent(functional.get('pass_rate'))}",
        f"- Tool selection accuracy: {_percent(routing.get('tool_selection_accuracy'))}",
        "",
        "## Dataset coverage",
        "",
        f"- Multi-turn dialogues: {datasets.get('conversations', 'n/a')}",
        f"- Dialogue turns: {datasets.get('conversation_turns', 'n/a')}",
        f"- RAG queries and faithfulness cases: {datasets.get('rag_queries', 'n/a')}",
        f"- Tool routing cases: {datasets.get('tool_prompts', 'n/a')}",
        "",
        "## Correctness",
        "",
        "Detailed per-case records, retrieved sources, tool calls, errors, and timings are preserved in `evaluation.json`.",
        "",
    ]
    if performance.get("latency"):
        lines.extend(["## Latency", "", *_latency_table(performance["latency"]), ""])
    if performance.get("concurrency"):
        concurrency = performance["concurrency"]
        lines.extend(
            [
                "## Throughput and concurrency",
                "",
                f"Maximum sustainable tested users: **{concurrency.get('max_sustainable_concurrent_users', 'n/a')}**",
                "",
                f"Observed breakpoint: **{concurrency.get('breakpoint_concurrent_users', 'not reached')}**",
                "",
                *_concurrency_table(concurrency),
                "",
            ]
        )
    failures = report.get("failures", [])
    lines.extend(
        [
            "## Failures and interpretation",
            "",
            *(f"- {failure}" for failure in failures),
            *( ["- No runner-level failures were recorded."] if not failures else [] ),
            "",
            "Heuristic scores are diagnostic signals, not substitutes for human review. Inspect failed case records before changing prompts, retrieval, or routing.",
            "",
            "## Reproducibility environment",
            "",
            f"- Platform: `{env['platform']}`",
            f"- Processor: `{env['processor']}`",
            f"- Logical CPUs: `{env['logical_cpu_count']}`",
            f"- Memory: `{env['memory_gb']} GiB`",
            f"- Python: `{env['python']}`",
            "- Dependencies: " + ", ".join(f"`{name}={version}`" for name, version in env["dependencies"].items()),
            "",
        ]
    )
    return "\n".join(lines)


def _latency_svg(latency: dict) -> str:
    values = [(name, data.get("end_to_end_ms", {}).get("median") or 0) for name, data in latency.items()]
    maximum = max((value for _, value in values), default=1) or 1
    bars = []
    for index, (name, value) in enumerate(values):
        y = 55 + index * 70
        width = 600 * value / maximum
        bars.append(f'<text x="10" y="{y + 20}" font-size="14">{name}</text>')
        bars.append(f'<rect x="160" y="{y}" width="{width:.1f}" height="28" fill="#2563eb" rx="4"/>')
        bars.append(f'<text x="{170 + width:.1f}" y="{y + 20}" font-size="13">{value:.1f} ms</text>')
    height = 90 + len(values) * 70
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" viewBox="0 0 900 {height}">'
        '<rect width="100%" height="100%" fill="white"/><text x="10" y="28" font-size="20" font-weight="bold">'
        'Median end-to-end latency</text>' + "".join(bars) + "</svg>"
    )


def write_reports(report: dict, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation.json"
    markdown_path = output_dir / "evaluation.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    markdown_path.write_text(build_markdown(report), encoding="utf-8")
    artifacts = {"json": str(json_path), "markdown": str(markdown_path)}
    latency = report.get("performance", {}).get("latency")
    if latency:
        graph_path = output_dir / "latency.svg"
        graph_path.write_text(_latency_svg(latency), encoding="utf-8")
        artifacts["latency_graph"] = str(graph_path)
    return artifacts
