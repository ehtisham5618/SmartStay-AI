"""HTTP and streaming WebSocket clients with timing instrumentation."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Optional


async def http_json(method: str, url: str, payload: Optional[dict] = None, timeout: float = 30) -> dict:
    def request():
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    return await asyncio.to_thread(request)


async def server_is_ready(base_url: str) -> tuple[bool, str]:
    try:
        response = await http_json("GET", f"{base_url.rstrip('/')}/health", timeout=5)
        return response.get("status") == "healthy", ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def websocket_turn(
    ws_url: str,
    message: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    timeout: float = 120,
) -> dict:
    import websockets

    session_id = session_id or f"eval-{uuid.uuid4()}"
    user_id = user_id or session_id
    token_times, tokens, context = [], [], {"sources": [], "tools": [], "metrics": {}, "errors": []}
    started = time.perf_counter()
    error = None

    try:
        async with websockets.connect(ws_url, open_timeout=10, max_size=16 * 1024 * 1024) as socket:
            await socket.send(json.dumps({"session_id": session_id, "user_id": user_id, "message": message}))
            async with asyncio.timeout(timeout):
                while True:
                    event = json.loads(await socket.recv())
                    if event.get("type") == "context":
                        context = event
                    elif event.get("type") == "token":
                        token_times.append(time.perf_counter())
                        tokens.append(event.get("content", ""))
                    elif event.get("type") == "done":
                        break
                    elif event.get("type") == "error":
                        error = event.get("message", "Unknown server error")
                        break
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    finished = time.perf_counter()
    gaps = [(right - left) * 1000 for left, right in zip(token_times, token_times[1:])]
    return {
        "session_id": session_id,
        "message": message,
        "response": "".join(tokens).strip(),
        "token_count": len(tokens),
        "ttft_ms": (token_times[0] - started) * 1000 if token_times else 0.0,
        "inter_token_ms": sum(gaps) / len(gaps) if gaps else 0.0,
        "e2e_ms": (finished - started) * 1000,
        "context": context,
        "error": error,
    }
