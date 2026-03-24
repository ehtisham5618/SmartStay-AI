"""Measure end-to-end voice protocol latency against a running SmartStay API."""

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import websockets


async def run_once(url: str, audio: bytes, mime_type: str, run_number: int) -> dict:
    started = time.perf_counter()
    measurements = {}
    async with websockets.connect(url, max_size=16 * 1024 * 1024) as socket:
        await socket.recv()  # voice_ready
        await socket.send(json.dumps({
            "type": "audio_start",
            "session_id": f"benchmark-{run_number}",
            "mime_type": mime_type,
        }))
        await socket.recv()  # recording_started
        await socket.send(audio)
        await socket.send(json.dumps({"type": "audio_end"}))

        while True:
            event = json.loads(await socket.recv())
            elapsed_ms = (time.perf_counter() - started) * 1_000
            if event["type"] == "transcript" and "transcript_ms" not in measurements:
                measurements["transcript_ms"] = elapsed_ms
            elif event["type"] == "token" and "first_token_ms" not in measurements:
                measurements["first_token_ms"] = elapsed_ms
            elif event["type"] == "audio" and "first_audio_ms" not in measurements:
                measurements["first_audio_ms"] = elapsed_ms
            elif event["type"] == "done":
                measurements["total_ms"] = elapsed_ms
                measurements["server"] = event.get("metrics", {})
                return measurements
            elif event["type"] == "error":
                raise RuntimeError(event["message"])


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path, help="Complete WebM, OGG, WAV, or MP4 speech recording")
    parser.add_argument("--url", default="ws://localhost:8000/ws/voice")
    parser.add_argument("--mime-type", default="audio/webm")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    audio = args.audio.read_bytes()
    results = [await run_once(args.url, audio, args.mime_type, index) for index in range(args.runs)]

    print(json.dumps(results, indent=2))
    for metric in ("transcript_ms", "first_token_ms", "first_audio_ms", "total_ms"):
        values = [result[metric] for result in results if metric in result]
        if values:
            print(f"{metric}: median={statistics.median(values):.0f} ms max={max(values):.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())

