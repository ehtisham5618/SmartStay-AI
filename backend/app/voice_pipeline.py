"""Local audio conversion, speech recognition, and speech synthesis."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import io
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path


class AudioConverter:
    """Normalize a complete browser recording to 16 kHz mono PCM WAV."""

    SUPPORTED_FORMATS = {"webm", "ogg", "wav", "mp4"}

    async def to_wav_16k(self, audio_bytes: bytes, source_extension: str = "webm") -> bytes:
        if not audio_bytes:
            raise ValueError("Audio payload is empty")
        extension = source_extension.lower().strip(".")
        if extension not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported audio format: {extension}")

        with tempfile.TemporaryDirectory(prefix="smartstay_audio_") as temp_dir:
            source = Path(temp_dir) / f"input.{extension}"
            target = Path(temp_dir) / "output.wav"
            source.write_bytes(audio_bytes)
            command = [
                "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                "-i", str(source), "-t", "30", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(target),
            ]
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    command,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("ffmpeg is required for browser audio conversion") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Audio conversion exceeded 20 seconds") from exc

            if result.returncode != 0 or not target.exists():
                detail = (result.stderr or "invalid audio").strip().splitlines()[-1]
                raise RuntimeError(f"Audio conversion failed: {detail}")
            return target.read_bytes()


class MoonshineASRService:
    """Lazy, reusable local Moonshine ASR service with four-worker admission."""

    def __init__(self, max_concurrency: int = 4):
        self._capacity = asyncio.Semaphore(max_concurrency)
        self._transcriber = None
        self._load_lock = threading.Lock()

    def _load(self):
        if self._transcriber is not None:
            return self._transcriber
        with self._load_lock:
            if self._transcriber is None:
                try:
                    moonshine = importlib.import_module("moonshine_voice")
                except ImportError as exc:
                    raise RuntimeError("Install moonshine-voice to enable local ASR") from exc
                model_path, model_arch = moonshine.get_model_for_language("en")
                self._transcriber = moonshine.Transcriber(
                    model_path=model_path,
                    model_arch=model_arch,
                )
        return self._transcriber

    async def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            raise ValueError("WAV payload is empty")

        def run() -> str:
            numpy = importlib.import_module("numpy")
            soundfile = importlib.import_module("soundfile")
            samples, sample_rate = soundfile.read(io.BytesIO(wav_bytes), dtype="float32")
            if getattr(samples, "ndim", 1) > 1:
                samples = numpy.mean(samples, axis=1)
            result = self._load().transcribe_without_streaming(
                samples.tolist(), sample_rate=int(sample_rate), flags=0
            )
            return " ".join(
                line.text.strip()
                for line in getattr(result, "lines", [])
                if getattr(line, "text", "").strip()
            )

        async with self._capacity:
            transcript = await asyncio.to_thread(run)
        if not transcript:
            raise RuntimeError("No speech was detected")
        return transcript[:2_000]


class PiperTTSService:
    """Lazy local Piper voice shared by concurrent synthesis requests."""

    def __init__(self, max_concurrency: int = 4):
        self._capacity = asyncio.Semaphore(max_concurrency)
        self._voice = None
        self._load_lock = threading.Lock()
        self._model_path = os.getenv("PIPER_MODEL_PATH", "").strip()
        self._config_path = os.getenv("PIPER_CONFIG_PATH", "").strip()
        self._length_scale = float(os.getenv("PIPER_LENGTH_SCALE", "1.0"))

    def _load(self):
        if self._voice is not None:
            return self._voice
        with self._load_lock:
            if self._voice is None:
                if not self._model_path or not Path(self._model_path).is_file():
                    raise RuntimeError("Set PIPER_MODEL_PATH to a local Piper .onnx voice")
                piper_voice = importlib.import_module("piper.voice")
                load_kwargs = {}
                if self._config_path:
                    if not Path(self._config_path).is_file():
                        raise RuntimeError("PIPER_CONFIG_PATH does not exist")
                    if "config_path" in inspect.signature(piper_voice.PiperVoice.load).parameters:
                        load_kwargs["config_path"] = self._config_path
                self._voice = piper_voice.PiperVoice.load(self._model_path, **load_kwargs)
        return self._voice

    async def synthesize_wav(self, text: str) -> bytes:
        clean_text = text.strip()
        if not clean_text:
            return b""

        def run() -> bytes:
            voice = self._load()
            synthesis_config = None
            try:
                config_module = importlib.import_module("piper.config")
                synthesis_config = config_module.SynthesisConfig(length_scale=self._length_scale)
            except (ImportError, AttributeError, TypeError):
                pass

            chunks = list(voice.synthesize(clean_text, syn_config=synthesis_config))
            if not chunks:
                return b""
            first = chunks[0]
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(int(getattr(first, "sample_channels", 1)))
                wav_file.setsampwidth(int(getattr(first, "sample_width", 2)))
                wav_file.setframerate(int(getattr(first, "sample_rate", 22_050)))
                wav_file.writeframes(
                    b"".join(getattr(chunk, "audio_int16_bytes", b"") for chunk in chunks)
                )
            return buffer.getvalue()

        async with self._capacity:
            return await asyncio.to_thread(run)


def audio_extension(mime_type: str) -> str:
    """Map browser MIME types to safe ffmpeg input extensions."""
    base_type = (mime_type or "audio/webm").split(";", 1)[0].lower()
    return {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mp4": "mp4",
    }.get(base_type, "webm")


def should_flush_sentence(buffer: str, first_fragment: bool = False) -> bool:
    """Flush natural phrases early enough for responsive spoken playback."""
    text = buffer.strip()
    if len(text) < 12:
        return False
    if text.endswith((".", "?", "!")):
        return True
    threshold = 32 if first_fragment else 120
    return len(text) >= threshold and text.endswith((" ", ",", ";", ":"))
