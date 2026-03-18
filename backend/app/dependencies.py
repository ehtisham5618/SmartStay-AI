"""Application service construction."""

import asyncio
from functools import lru_cache

from conversation.memory_manager import MemoryManager
from conversation.prompt_builder import PromptBuilder
from conversation.session_manager import SessionManager
from llm.ollama_client import OllamaClient
from rag.retriever import RAGRetriever
from tools.orchestrator import ToolOrchestrator

from .websocket_manager import WebSocketManager
from .voice_pipeline import AudioConverter, MoonshineASRService, PiperTTSService


@lru_cache
def get_websocket_manager() -> WebSocketManager:
    return WebSocketManager()


@lru_cache
def get_ollama_client() -> OllamaClient:
    return OllamaClient()


@lru_cache
def get_memory_manager() -> MemoryManager:
    return MemoryManager(max_messages=12)


@lru_cache
def get_prompt_builder() -> PromptBuilder:
    return PromptBuilder()


@lru_cache
def get_retriever() -> RAGRetriever:
    return RAGRetriever()


@lru_cache
def get_tool_orchestrator() -> ToolOrchestrator:
    return ToolOrchestrator()


@lru_cache
def get_session_manager() -> SessionManager:
    return SessionManager(
        get_ollama_client(),
        get_memory_manager(),
        get_prompt_builder(),
        get_retriever(),
        get_tool_orchestrator(),
    )


@lru_cache
def get_audio_converter() -> AudioConverter:
    return AudioConverter()


@lru_cache
def get_asr_service() -> MoonshineASRService:
    return MoonshineASRService(max_concurrency=4)


@lru_cache
def get_tts_service() -> PiperTTSService:
    return PiperTTSService(max_concurrency=4)


@lru_cache
def get_voice_turn_capacity() -> asyncio.Semaphore:
    """Limit the complete CPU-heavy voice pipeline to four active users."""
    return asyncio.Semaphore(4)
