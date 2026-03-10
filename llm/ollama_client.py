"""Async client for a locally running Ollama model."""

from __future__ import annotations

import json
import os
from typing import AsyncGenerator, Optional

import httpx


class OllamaClient:
    def __init__(self, model_name: Optional[str] = None, base_url: Optional[str] = None):
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "smartstay-qwen")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.generate_url = f"{self.base_url}/api/generate"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "keep_alive": "30m",
            "options": {"num_ctx": 4096, "num_predict": 200, "temperature": 0.3},
        }
        try:
            async with self._client.stream("POST", self.generate_url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get("response"):
                        yield event["response"]
                    if event.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise RuntimeError("Cannot connect to local Ollama server") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Ollama returned HTTP {exc.response.status_code}") from exc

    async def close(self) -> None:
        await self._client.aclose()
