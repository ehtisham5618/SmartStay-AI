"""Session lifecycle plus concurrent RAG and tool preprocessing."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Optional


class SessionManager:
    def __init__(self, ollama_client, memory_manager, prompt_builder, retriever=None, tool_orchestrator=None):
        self.ollama_client = ollama_client
        self.memory_manager = memory_manager
        self.prompt_builder = prompt_builder
        self.retriever = retriever
        self.tool_orchestrator = tool_orchestrator
        self.sessions: Dict[str, dict] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def create_session(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> str:
        session_id = session_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.sessions.setdefault(
            session_id,
            {"user_id": user_id or session_id, "created_at": now, "last_active": now},
        )
        self.memory_manager.create_session(session_id)
        self._locks.setdefault(session_id, asyncio.Lock())
        return session_id

    def ensure_session(self, session_id: Optional[str], user_id: Optional[str] = None) -> str:
        if session_id and session_id in self.sessions:
            if user_id:
                self.sessions[session_id]["user_id"] = user_id
            return session_id
        return self.create_session(user_id=user_id, session_id=session_id)

    async def _retrieve(self, message: str) -> tuple[list, float, Optional[str]]:
        if self.retriever is None:
            return [], 0.0, None
        if hasattr(self.retriever, "should_retrieve") and not self.retriever.should_retrieve(message):
            return [], 0.0, None
        started = time.perf_counter()
        try:
            results = await asyncio.to_thread(self.retriever.retrieve, message, 3)
            return results, (time.perf_counter() - started) * 1_000, None
        except Exception as exc:
            return [], (time.perf_counter() - started) * 1_000, str(exc)

    async def _tools(self, message: str, user_id: str) -> tuple[list, float, Optional[str]]:
        if self.tool_orchestrator is None:
            return [], 0.0, None
        started = time.perf_counter()
        try:
            results = await self.tool_orchestrator.execute_for_message(message, user_id)
            return [result.as_dict() for result in results], (time.perf_counter() - started) * 1_000, None
        except Exception as exc:
            return [], (time.perf_counter() - started) * 1_000, str(exc)

    async def stream_events(self, session_id: str, user_message: str) -> AsyncGenerator[dict, None]:
        if session_id not in self.sessions:
            raise ValueError("Unknown session")

        async with self._locks[session_id]:
            history = self.memory_manager.get_active_context(session_id)
            user_id = self.sessions[session_id].get("user_id") or session_id
            preprocessing_started = time.perf_counter()
            profile_task = (
                asyncio.create_task(self.tool_orchestrator.get_profile(user_id))
                if self.tool_orchestrator else None
            )
            retrieval_result, tool_result = await asyncio.gather(
                self._retrieve(user_message), self._tools(user_message, user_id)
            )
            profile = await profile_task if profile_task else None
            retrieved, retrieval_ms, rag_error = retrieval_result
            tools, tool_ms, tool_error = tool_result
            context_event = {
                "type": "context",
                "sources": [
                    {"source": item.get("source"), "title": item.get("title"), "score": round(item.get("score", 0), 3)}
                    for item in retrieved
                ],
                "tools": tools,
                "metrics": {
                    "retrieval_ms": round(retrieval_ms, 2),
                    "tool_ms": round(tool_ms, 2),
                    "preprocessing_ms": round((time.perf_counter() - preprocessing_started) * 1_000, 2),
                },
                "errors": [error for error in (rag_error, tool_error) if error],
            }
            yield context_event

            prompt = self.prompt_builder.build_prompt(history, user_message, retrieved, tools, profile)
            chunks = []
            async for token in self.ollama_client.generate_stream(prompt):
                chunks.append(token)
                yield {"type": "token", "content": token}

            response = "".join(chunks).strip()
            if response:
                self.memory_manager.add_message(session_id, "user", user_message)
                self.memory_manager.add_message(session_id, "assistant", response)
                if self.tool_orchestrator:
                    await self.tool_orchestrator.record_interaction(
                        user_id, f"Guest: {user_message[:120]} | Assistant: {response[:140]}"
                    )
            self.sessions[session_id]["last_active"] = datetime.now(timezone.utc).isoformat()

    async def stream_message(self, session_id: str, user_message: str) -> AsyncGenerator[str, None]:
        async for event in self.stream_events(session_id, user_message):
            if event["type"] == "token":
                yield event["content"]

    async def process_message(self, session_id: str, user_message: str) -> str:
        return "".join([token async for token in self.stream_message(session_id, user_message)])

    def delete_session(self, session_id: str) -> bool:
        existed = self.sessions.pop(session_id, None) is not None
        self._locks.pop(session_id, None)
        self.memory_manager.delete_session(session_id)
        return existed
