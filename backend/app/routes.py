"""REST and WebSocket endpoints for SmartStay AI."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .dependencies import (
    get_asr_service,
    get_audio_converter,
    get_session_manager,
    get_retriever,
    get_tts_service,
    get_tool_orchestrator,
    get_voice_turn_capacity,
    get_websocket_manager,
)
from .voice_pipeline import audio_extension, should_flush_sentence

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    sources: list[dict] = Field(default_factory=list)
    tools: list[dict] = Field(default_factory=list)


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=3, ge=3, le=5)


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    sessions = get_session_manager()
    session_id = sessions.ensure_session(request.session_id, request.user_id)
    chunks, context = [], {"sources": [], "tools": []}
    async for event in sessions.stream_events(session_id, request.message):
        if event["type"] == "context":
            context = event
        elif event["type"] == "token":
            chunks.append(event["content"])
    return ChatResponse(
        session_id=session_id,
        response="".join(chunks),
        sources=context["sources"],
        tools=context["tools"],
    )


@router.post("/api/retrieve")
async def retrieve(request: RetrieveRequest) -> dict:
    started = time.perf_counter()
    try:
        results = await asyncio.to_thread(get_retriever().retrieve, request.query, request.top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"results": results, "latency_ms": round((time.perf_counter() - started) * 1_000, 2)}


@router.get("/api/tools")
async def list_tools() -> dict:
    return {"tools": get_tool_orchestrator().registry.schemas(), "mcp_endpoint": "http://localhost:8001/mcp"}


@router.delete("/api/sessions/{session_id}")
async def reset_session(session_id: str) -> dict:
    return {"deleted": get_session_manager().delete_session(session_id)}


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    connections = get_websocket_manager()
    sessions = get_session_manager()
    connection_id: Optional[str] = None
    await websocket.accept()

    try:
        while True:
            payload = await websocket.receive_json()
            message = str(payload.get("message", "")).strip()
            if not message or len(message) > 2_000:
                await websocket.send_json({"type": "error", "message": "Message must contain 1–2000 characters."})
                continue

            session_id = sessions.ensure_session(payload.get("session_id"), payload.get("user_id"))
            if connection_id != session_id:
                if connection_id:
                    await connections.disconnect(connection_id, close_socket=False)
                await connections.connect(session_id, websocket, accept=False)
                connection_id = session_id

            await websocket.send_json({"type": "start", "session_id": session_id})
            try:
                async for event in sessions.stream_events(session_id, message):
                    await websocket.send_json(event)
                await websocket.send_json({"type": "done", "session_id": session_id})
            except RuntimeError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", connection_id)
    except Exception:
        logger.exception("Unexpected WebSocket failure")
        try:
            await websocket.send_json({"type": "error", "message": "Unexpected server error"})
        except Exception:
            pass
    finally:
        if connection_id:
            await connections.disconnect(connection_id, close_socket=False)


async def _send_event(websocket: WebSocket, send_lock: asyncio.Lock, event: dict) -> None:
    async with send_lock:
        await websocket.send_json(event)


async def _tts_worker(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    fragments: asyncio.Queue,
    timing: dict,
) -> None:
    """Synthesize ordered phrases while LLM text is still streaming."""
    sequence = 0
    tts = get_tts_service()
    while True:
        fragment = await fragments.get()
        if fragment is None:
            break
        try:
            wav_bytes = await tts.synthesize_wav(fragment)
        except Exception as exc:  # speech should not discard the text response
            await _send_event(
                websocket,
                send_lock,
                {"type": "audio_error", "message": str(exc)},
            )
            return
        if not wav_bytes:
            continue
        if "first_audio_at" not in timing:
            timing["first_audio_at"] = time.perf_counter()
        await _send_event(
            websocket,
            send_lock,
            {
                "type": "audio",
                "sequence": sequence,
                "mime_type": "audio/wav",
                "content": base64.b64encode(wav_bytes).decode("ascii"),
            },
        )
        sequence += 1
    await _send_event(websocket, send_lock, {"type": "audio_done", "chunks": sequence})


async def _process_voice_turn(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    audio_bytes: bytes,
    mime_type: str,
    requested_session_id: Optional[str],
    user_id: Optional[str],
) -> None:
    started_at = time.perf_counter()
    timing = {}
    async with get_voice_turn_capacity():
        await _send_event(websocket, send_lock, {"type": "status", "stage": "transcribing"})
        wav_bytes = await get_audio_converter().to_wav_16k(
            audio_bytes,
            audio_extension(mime_type),
        )
        transcript = await get_asr_service().transcribe(wav_bytes)
        asr_finished_at = time.perf_counter()

        sessions = get_session_manager()
        session_id = sessions.ensure_session(requested_session_id, user_id)
        await _send_event(
            websocket,
            send_lock,
            {"type": "transcript", "session_id": session_id, "content": transcript},
        )
        await _send_event(websocket, send_lock, {"type": "status", "stage": "responding"})

        fragments: asyncio.Queue = asyncio.Queue()
        tts_task = asyncio.create_task(_tts_worker(websocket, send_lock, fragments, timing))
        phrase_buffer = ""
        first_fragment = True
        first_token_at = None
        try:
            async for event in sessions.stream_events(session_id, transcript):
                if event["type"] == "context":
                    await _send_event(websocket, send_lock, event)
                    continue
                token = event["content"]
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                phrase_buffer += token
                await _send_event(websocket, send_lock, {"type": "token", "content": token})
                if should_flush_sentence(phrase_buffer, first_fragment):
                    await fragments.put(phrase_buffer.strip())
                    phrase_buffer = ""
                    first_fragment = False
            if phrase_buffer.strip():
                await fragments.put(phrase_buffer.strip())
        finally:
            await fragments.put(None)
            await tts_task

        finished_at = time.perf_counter()
        metrics = {
            "asr_ms": round((asr_finished_at - started_at) * 1_000),
            "first_token_ms": round(((first_token_at or finished_at) - started_at) * 1_000),
            "total_ms": round((finished_at - started_at) * 1_000),
        }
        if timing.get("first_audio_at"):
            metrics["first_audio_ms"] = round((timing["first_audio_at"] - started_at) * 1_000)
        await _send_event(
            websocket,
            send_lock,
            {"type": "done", "session_id": session_id, "metrics": metrics},
        )


@router.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket) -> None:
    """Receive one complete browser recording and stream transcript, text, and WAV phrases."""
    await websocket.accept()
    send_lock = asyncio.Lock()
    recording = bytearray()
    metadata: dict = {}

    try:
        await websocket.send_json({"type": "voice_ready", "max_audio_bytes": MAX_AUDIO_BYTES})
        while True:
            message = await websocket.receive()
            if message.get("bytes") is not None:
                if not metadata:
                    await _send_event(websocket, send_lock, {"type": "error", "message": "Send audio_start first"})
                    continue
                recording.extend(message["bytes"])
                if len(recording) > MAX_AUDIO_BYTES:
                    recording.clear()
                    metadata.clear()
                    await _send_event(websocket, send_lock, {"type": "error", "message": "Recording exceeds 8 MB"})
                continue

            text = message.get("text")
            if text is None:
                continue
            payload = json.loads(text)
            event_type = payload.get("type")
            if event_type == "audio_start":
                recording.clear()
                metadata = {
                    "session_id": payload.get("session_id"),
                    "user_id": payload.get("user_id"),
                    "mime_type": str(payload.get("mime_type", "audio/webm")),
                }
                await _send_event(websocket, send_lock, {"type": "recording_started"})
            elif event_type == "audio_end":
                if not recording:
                    await _send_event(websocket, send_lock, {"type": "error", "message": "Recording is empty"})
                    continue
                captured_audio = bytes(recording)
                captured_metadata = metadata.copy()
                recording.clear()
                metadata.clear()
                try:
                    await _process_voice_turn(
                        websocket,
                        send_lock,
                        captured_audio,
                        captured_metadata.get("mime_type", "audio/webm"),
                        captured_metadata.get("session_id"),
                        captured_metadata.get("user_id"),
                    )
                except Exception as exc:
                    logger.exception("Voice turn failed")
                    await _send_event(websocket, send_lock, {"type": "error", "message": str(exc)})
            elif event_type == "ping":
                await _send_event(websocket, send_lock, {"type": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        logger.info("Voice WebSocket disconnected")
    except json.JSONDecodeError:
        await _send_event(websocket, send_lock, {"type": "error", "message": "Invalid JSON control message"})
