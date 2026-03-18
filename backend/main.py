"""FastAPI entry point for SmartStay AI."""

import asyncio
import importlib.util
import logging
import os
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .app.dependencies import get_ollama_client, get_retriever
from .app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SmartStay AI",
        description="Local hotel front-desk conversational API",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/")
    async def root() -> dict:
        return {"service": "SmartStay AI", "status": "online"}

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "healthy",
            "inference": "local-ollama",
            "voice_endpoint": "/ws/voice",
            "max_concurrent_voice_users": 4,
            "rag_documents": 50,
            "rag_top_k": 3,
            "tools": 4,
            "mcp_endpoint": "http://localhost:8001/mcp",
        }

    @app.get("/health/voice")
    async def voice_health() -> dict:
        model_path = os.getenv("PIPER_MODEL_PATH", "")
        checks = {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "moonshine": importlib.util.find_spec("moonshine_voice") is not None,
            "piper": importlib.util.find_spec("piper") is not None,
            "piper_model": bool(model_path and Path(model_path).is_file()),
        }
        return {"ready": all(checks.values()), "components": checks}

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await get_ollama_client().close()

    @app.on_event("startup")
    async def warm_retrieval() -> None:
        try:
            await asyncio.to_thread(get_retriever().retrieve, "hotel check-in policy", 3)
            logging.getLogger(__name__).info("RAG index and embedding model warmed")
        except Exception as exc:
            logging.getLogger(__name__).warning("RAG warm-up skipped: %s", exc)

    return app


app = create_app()
