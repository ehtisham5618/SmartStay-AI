"""Persistent SQLite customer profile tool."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


CRM_SCHEMA = {
    "name": "crm_profile",
    "description": "Get, create, update, or append an interaction to a persistent guest profile.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {"type": "string", "enum": ["get", "upsert", "delete", "record_interaction"]},
            "user_id": {"type": "string"},
            "name": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "preference": {"type": "string"},
            "interaction": {"type": "string"},
        },
        "required": ["action", "user_id"],
    },
}


class CRMStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(os.getenv("CRM_DB_PATH", "data/crm.sqlite3"))
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS guests (
                    user_id TEXT PRIMARY KEY,
                    name TEXT, email TEXT, phone TEXT,
                    preferences TEXT NOT NULL DEFAULT '[]',
                    interactions TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.commit()

    def _get_sync(self, user_id: str) -> Optional[dict]:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM guests WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["preferences"] = json.loads(result["preferences"])
        result["interactions"] = json.loads(result["interactions"])[-10:]
        return result

    async def get(self, user_id: str) -> Optional[dict]:
        return await asyncio.to_thread(self._get_sync, user_id)

    def _upsert_sync(self, user_id: str, fields: dict) -> dict:
        current = self._get_sync(user_id) or {
            "name": None, "email": None, "phone": None, "preferences": [], "interactions": []
        }
        preferences = list(current.get("preferences", []))
        if fields.get("preference") and fields["preference"] not in preferences:
            preferences.append(fields["preference"])
        values = {
            "name": fields.get("name") or current.get("name"),
            "email": fields.get("email") or current.get("email"),
            "phone": fields.get("phone") or current.get("phone"),
            "preferences": json.dumps(preferences[-20:]),
            "interactions": json.dumps(current.get("interactions", [])),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO guests(user_id,name,email,phone,preferences,interactions,updated_at)
                   VALUES(:user_id,:name,:email,:phone,:preferences,:interactions,:updated_at)
                   ON CONFLICT(user_id) DO UPDATE SET
                   name=excluded.name,email=excluded.email,phone=excluded.phone,
                   preferences=excluded.preferences,updated_at=excluded.updated_at""",
                {"user_id": user_id, **values},
            )
            connection.commit()
        return self._get_sync(user_id)

    async def upsert(self, user_id: str, **fields) -> dict:
        return await asyncio.to_thread(self._upsert_sync, user_id, fields)

    def _record_sync(self, user_id: str, interaction: str) -> dict:
        current = self._get_sync(user_id) or self._upsert_sync(user_id, {})
        history = list(current.get("interactions", []))
        history.append({"at": datetime.now(timezone.utc).isoformat(), "summary": interaction[:300]})
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "UPDATE guests SET interactions = ?, updated_at = ? WHERE user_id = ?",
                (json.dumps(history[-50:]), datetime.now(timezone.utc).isoformat(), user_id),
            )
            connection.commit()
        return self._get_sync(user_id)

    async def record(self, user_id: str, interaction: str) -> dict:
        return await asyncio.to_thread(self._record_sync, user_id, interaction)

    def _delete_sync(self, user_id: str) -> bool:
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM guests WHERE user_id = ?", (user_id,))
            connection.commit()
            return cursor.rowcount > 0

    async def delete(self, user_id: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, user_id)


_default_store: Optional[CRMStore] = None


def get_crm_store() -> CRMStore:
    global _default_store
    if _default_store is None:
        _default_store = CRMStore()
    return _default_store


async def crm_profile(
    action: str,
    user_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    preference: Optional[str] = None,
    interaction: Optional[str] = None,
) -> dict:
    store = get_crm_store()
    if action == "get":
        profile = await store.get(user_id)
        return {"ok": True, "found": profile is not None, "profile": profile}
    if action == "upsert":
        profile = await store.upsert(
            user_id, name=name, email=email, phone=phone, preference=preference
        )
        return {"ok": True, "profile": profile}
    if action == "delete":
        return {"ok": True, "deleted": await store.delete(user_id)}
    if action == "record_interaction" and interaction:
        return {"ok": True, "profile": await store.record(user_id, interaction)}
    return {"ok": False, "error": "Invalid CRM action or missing interaction"}
