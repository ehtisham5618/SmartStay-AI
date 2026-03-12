"""Local iCalendar booking-event writer."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


CALENDAR_SCHEMA = {
    "name": "create_calendar_event",
    "description": "Create a local .ics hold for requested hotel stay dates.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "user_id": {"type": "string"},
            "guest_name": {"type": "string"},
            "room_type": {"type": "string"},
            "check_in": {"type": "string"},
            "check_out": {"type": "string"},
        },
        "required": ["user_id", "room_type", "check_in", "check_out"],
    },
}


CALENDAR_DIR = Path("calendars")
_write_lock = threading.RLock()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _write_event(record: dict) -> Path:
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    safe_user = re.sub(r"[^a-zA-Z0-9_-]", "_", record["user_id"])[:50] or "guest"
    path = CALENDAR_DIR / f"{safe_user}_{record['event_id']}.ics"
    content = "\r\n".join(
        [
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SmartStay AI//EN",
            "BEGIN:VEVENT", f"UID:{record['event_id']}",
            f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;VALUE=DATE:{record['check_in'].replace('-', '')}",
            f"DTEND;VALUE=DATE:{record['check_out'].replace('-', '')}",
            f"SUMMARY:{_escape(record['summary'])}",
            f"DESCRIPTION:{_escape(record['description'])}",
            "END:VEVENT", "END:VCALENDAR", "",
        ]
    )
    with _write_lock:
        path.write_text(content, encoding="utf-8", newline="")
        log_path = CALENDAR_DIR / "bookings.jsonl"
        with log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")
    return path


async def create_calendar_event(
    user_id: str,
    room_type: str,
    check_in: str,
    check_out: str,
    guest_name: Optional[str] = "Guest",
) -> dict:
    try:
        start, end = date.fromisoformat(check_in), date.fromisoformat(check_out)
    except ValueError:
        return {"ok": False, "error": "Dates must use YYYY-MM-DD"}
    if end <= start:
        return {"ok": False, "error": "Check-out must be after check-in"}
    event_id = str(uuid.uuid4())
    record = {
        "event_id": event_id,
        "user_id": user_id,
        "guest_name": guest_name or "Guest",
        "room_type": room_type,
        "check_in": check_in,
        "check_out": check_out,
        "summary": f"SmartStay {room_type} stay request",
        "description": "Local calendar hold; hotel staff must still confirm availability.",
    }
    path = await asyncio.to_thread(_write_event, record)
    return {"ok": True, "event_id": event_id, "calendar_file": str(path), **record}

