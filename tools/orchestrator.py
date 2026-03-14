"""Low-latency intent routing and asynchronous tool execution."""

from __future__ import annotations

import asyncio
import re
from typing import List, Optional

from . import create_registry
from .registry import ToolRegistry, ToolResult


class ToolOrchestrator:
    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or create_registry()

    @staticmethod
    def _dates(message: str) -> list[str]:
        return re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message)

    @staticmethod
    def _room_type(message: str) -> Optional[str]:
        match = re.search(r"\b(standard|deluxe|suite)\b", message, re.IGNORECASE)
        return match.group(1).title() if match else None

    def plan(self, message: str, user_id: str) -> List[tuple[str, dict]]:
        """Translate clear user intents into schema-valid calls before generation."""
        lower = message.lower()
        dates = self._dates(message)
        room_type = self._room_type(message)
        calls: List[tuple[str, dict]] = []

        crm_fields = {}
        patterns = {
            "name": r"\bmy name is\s+([A-Za-z][A-Za-z .'-]{1,60})",
            "email": r"\bmy email(?: address)? is\s+([^\s,;]+@[^\s,;]+)",
            "phone": r"\bmy phone(?: number)? is\s+([+\d][\d ()-]{6,25})",
            "preference": r"\b(?:i prefer|my preference is)\s+(.{2,100})",
        }
        for field, pattern in patterns.items():
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                crm_fields[field] = match.group(1).strip(" .!?")
        if crm_fields:
            calls.append(("crm_profile", {"action": "upsert", "user_id": user_id, **crm_fields}))
        elif any(phrase in lower for phrase in ("my profile", "my name", "my email", "my phone", "remember me")):
            calls.append(("crm_profile", {"action": "get", "user_id": user_id}))

        if room_type and len(dates) >= 2 and any(word in lower for word in ("cost", "price", "how much", "calculate")):
            guests_match = re.search(r"\b(\d{1,2})\s+(?:guests?|people)\b", lower)
            calls.append(
                (
                    "calculate_room_cost",
                    {
                        "room_type": room_type,
                        "check_in": dates[0],
                        "check_out": dates[1],
                        "guests": int(guests_match.group(1)) if guests_match else 1,
                    },
                )
            )

        if len(dates) >= 2 and any(word in lower for word in ("book", "reserve", "calendar", "schedule")):
            calls.append(
                (
                    "create_calendar_event",
                    {
                        "user_id": user_id,
                        "room_type": room_type or "Standard",
                        "check_in": dates[0],
                        "check_out": dates[1],
                    },
                )
            )

        if any(word in lower for word in ("weather", "forecast", "temperature", "rain")):
            city_match = re.search(
                r"\b(?:weather|forecast|temperature)(?:\s+(?:in|for))?\s+([A-Za-z][A-Za-z ]{1,40}?)(?=\s+on\s+\d{4}-|[?.!,]|$)",
                message,
                re.IGNORECASE,
            )
            city = city_match.group(1).strip() if city_match else "Islamabad"
            arguments = {"city": city}
            if dates:
                arguments["date"] = dates[0]
            calls.append(("get_weather", arguments))

        unique = []
        seen = set()
        for call in calls:
            if call[0] not in seen:
                unique.append(call)
                seen.add(call[0])
        return unique

    async def execute_for_message(self, message: str, user_id: str) -> List[ToolResult]:
        calls = self.plan(message, user_id)
        if not calls:
            return []
        return list(await asyncio.gather(*(self.registry.execute(name, args) for name, args in calls)))

    async def get_profile(self, user_id: str) -> Optional[dict]:
        result = await self.registry.execute("crm_profile", {"action": "get", "user_id": user_id})
        return result.output.get("profile") if result.ok else None

    async def record_interaction(self, user_id: str, summary: str) -> None:
        await self.registry.execute(
            "crm_profile",
            {"action": "record_interaction", "user_id": user_id, "interaction": summary[:300]},
        )

