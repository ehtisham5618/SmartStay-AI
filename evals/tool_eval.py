"""Direct tool correctness and intent-routing accuracy."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools import calendar_tool
from tools.calculator import calculate_room_cost
from tools.calendar_tool import create_calendar_event
from tools.crm import CRMStore
from tools.orchestrator import ToolOrchestrator
from tools.weather import get_weather

from .datasets import load_tool_invocations
from .metrics import safe_divide


def _arguments_match(actual: dict, expected: dict) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


async def evaluate_tool_routing() -> dict:
    orchestrator = ToolOrchestrator()
    cases = load_tool_invocations()
    details = []
    correct_selection = correct_arguments = required_count = false_positives = negative_count = 0

    for case in cases:
        calls = orchestrator.plan(case["prompt"], "eval-user")
        call_map = {name: arguments for name, arguments in calls}
        expected = case["expected_tool"]
        if expected is None:
            negative_count += 1
            selection_ok = not calls
            false_positives += int(bool(calls))
            arguments_ok = selection_ok
        else:
            required_count += 1
            selection_ok = expected in call_map
            arguments_ok = selection_ok and _arguments_match(call_map[expected], case["expected_args"])
            correct_arguments += int(arguments_ok)
        correct_selection += int(selection_ok)
        details.append(
            {
                "id": case["id"],
                "expected_tool": expected,
                "actual_tools": list(call_map),
                "selection_ok": selection_ok,
                "arguments_ok": arguments_ok,
            }
        )

    return {
        "cases": len(cases),
        "tool_selection_accuracy": safe_divide(correct_selection, len(cases)),
        "argument_accuracy_when_required": safe_divide(correct_arguments, required_count),
        "false_positive_rate": safe_divide(false_positives, negative_count),
        "details": details,
    }


async def evaluate_tool_functions(include_network: bool = False) -> dict:
    checks = []

    def record(name: str, passed: bool, detail: str = ""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory() as directory:
        crm = CRMStore(Path(directory) / "crm.sqlite3")
        created = await crm.upsert("crud-user", name="Alice", preference="quiet room")
        record("CRM create", created.get("name") == "Alice")
        fetched = await crm.get("crud-user")
        record("CRM read", fetched is not None and "quiet room" in fetched["preferences"])
        updated = await crm.upsert("crud-user", phone="12345")
        record("CRM update", updated.get("phone") == "12345")
        deleted = await crm.delete("crud-user")
        remaining = await crm.get("crud-user")
        record("CRM delete", deleted and remaining is None)

    valid_cost = await calculate_room_cost("Deluxe", "2026-06-01", "2026-06-04", 2)
    invalid_cost = await calculate_room_cost("Deluxe", "2026-06-04", "2026-06-01", 2)
    record("Calculator valid", valid_cost.get("ok") and valid_cost.get("total_usd") == 450.0)
    record("Calculator invalid", not invalid_cost.get("ok"))

    original_directory = calendar_tool.CALENDAR_DIR
    with tempfile.TemporaryDirectory() as directory:
        calendar_tool.CALENDAR_DIR = Path(directory)
        try:
            valid_event = await create_calendar_event(
                "eval-user", "Suite", "2026-06-01", "2026-06-03", "Alice"
            )
            invalid_event = await create_calendar_event(
                "eval-user", "Suite", "2026-06-03", "2026-06-01", "Alice"
            )
            record(
                "Calendar valid",
                valid_event.get("ok") and Path(valid_event["calendar_file"]).is_file(),
            )
            record("Calendar invalid", not invalid_event.get("ok"))
        finally:
            calendar_tool.CALENDAR_DIR = original_directory

    invalid_weather = await get_weather("Islamabad", "not-a-date")
    record("Weather invalid", not invalid_weather.get("ok"))
    if include_network:
        valid_weather = await get_weather("Islamabad")
        record("Weather valid network", valid_weather.get("ok"), valid_weather.get("error", ""))
    else:
        checks.append({"name": "Weather valid network", "passed": None, "detail": "Skipped; enable live network checks"})

    executed = [check for check in checks if check["passed"] is not None]
    return {
        "checks": checks,
        "passed": sum(check["passed"] for check in executed),
        "executed": len(executed),
        "pass_rate": safe_divide(sum(check["passed"] for check in executed), len(executed)),
    }


async def evaluate_tools(include_network: bool = False) -> dict:
    return {
        "functional": await evaluate_tool_functions(include_network),
        "routing": await evaluate_tool_routing(),
    }
