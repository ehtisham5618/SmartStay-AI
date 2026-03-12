"""Deterministic hotel stay price calculator."""

from datetime import date
from typing import Optional


CALCULATOR_SCHEMA = {
    "name": "calculate_room_cost",
    "description": "Calculate the room total from room type, dates, and guest count.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "room_type": {"type": "string", "enum": ["Standard", "Deluxe", "Suite"]},
            "check_in": {"type": "string"},
            "check_out": {"type": "string"},
            "guests": {"type": "integer", "minimum": 1},
        },
        "required": ["room_type", "check_in", "check_out"],
    },
}


async def calculate_room_cost(
    room_type: str, check_in: str, check_out: str, guests: Optional[int] = 1
) -> dict:
    prices = {"standard": 70.0, "deluxe": 150.0, "suite": 300.0}
    key = room_type.lower()
    if key not in prices:
        return {"ok": False, "error": "Room type must be Standard, Deluxe, or Suite"}
    try:
        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    except ValueError:
        return {"ok": False, "error": "Dates must use YYYY-MM-DD"}
    if nights < 1:
        return {"ok": False, "error": "Check-out must be after check-in"}
    guest_count = int(guests or 1)
    surcharge = 0.15 if key == "suite" and guest_count > 2 else 0.0
    base = nights * prices[key]
    total = round(base * (1 + surcharge), 2)
    return {
        "ok": True,
        "room_type": room_type.title(),
        "nights": nights,
        "guests": guest_count,
        "nightly_rate_usd": prices[key],
        "occupancy_surcharge_usd": round(total - base, 2),
        "total_usd": total,
    }

