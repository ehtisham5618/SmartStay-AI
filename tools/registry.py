"""Async schema-defined tool registry with validation and timeouts."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Awaitable[dict]]
    timeout_seconds: float = 6.0


@dataclass
class ToolResult:
    name: str
    ok: bool
    output: dict
    latency_ms: float

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "output": self.output, "latency_ms": round(self.latency_ms, 2)}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, schema: dict, handler: Callable[..., Awaitable[dict]], timeout_seconds: float = 6.0) -> None:
        self._tools[schema["name"]] = ToolSpec(
            schema["name"], schema["description"], schema["input_schema"], handler, timeout_seconds
        )

    def schemas(self) -> List[dict]:
        return [
            {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
            for spec in self._tools.values()
        ]

    def _validate(self, spec: ToolSpec, arguments: dict) -> None:
        schema = spec.input_schema
        missing = [key for key in schema.get("required", []) if arguments.get(key) is None]
        if missing:
            raise ValueError(f"Missing required arguments: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            unknown = set(arguments) - set(schema.get("properties", {}))
            if unknown:
                raise ValueError(f"Unknown arguments: {', '.join(sorted(unknown))}")
        for key, value in arguments.items():
            definition = schema.get("properties", {}).get(key, {})
            if "enum" in definition and value not in definition["enum"]:
                raise ValueError(f"Invalid {key}: expected one of {definition['enum']}")
            expected = definition.get("type")
            valid_type = {
                "string": lambda item: isinstance(item, str),
                "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
                "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
                "object": lambda item: isinstance(item, dict),
                "array": lambda item: isinstance(item, list),
                "boolean": lambda item: isinstance(item, bool),
            }.get(expected)
            if valid_type and not valid_type(value):
                raise ValueError(f"Invalid {key}: expected {expected}")
            if "minimum" in definition and value < definition["minimum"]:
                raise ValueError(f"Invalid {key}: minimum is {definition['minimum']}")

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        started = time.perf_counter()
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(name, False, {"error": "Unknown tool"}, 0)
        try:
            self._validate(spec, arguments)
            output = await asyncio.wait_for(spec.handler(**arguments), timeout=spec.timeout_seconds)
            return ToolResult(name, bool(output.get("ok")), output, (time.perf_counter() - started) * 1000)
        except (ValueError, asyncio.TimeoutError) as exc:
            return ToolResult(name, False, {"error": str(exc) or "Tool timed out"}, (time.perf_counter() - started) * 1000)
        except Exception as exc:
            return ToolResult(name, False, {"error": f"Tool failed: {type(exc).__name__}"}, (time.perf_counter() - started) * 1000)
