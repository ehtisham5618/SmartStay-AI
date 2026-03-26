# Assignment 2: Local Voice Interface

SmartStay AI now accepts speech and responds with both streaming text and locally synthesized audio. The pipeline remains domain-restricted and uses no tools or retrieval system.

## Pipeline

```text
Browser microphone (WebM/Opus)
  -> binary WebSocket upload
  -> ffmpeg (16 kHz mono WAV)
  -> Moonshine ASR on CPU
  -> existing prompt + bounded session memory
  -> quantized Qwen through local Ollama
  -> sentence buffer
  -> Piper TTS on CPU
  -> ordered WAV events
  -> browser playback queue
```

The Moonshine and Piper models are lazy-loaded once and reused. Blocking conversion and model inference run in worker threads. ASR, TTS, and complete voice turns each have a four-user concurrency limit. Each session still has its own turn lock, preserving message order when text and voice share a session.

## Voice WebSocket protocol

Connect to `WS /ws/voice`. The server first emits `voice_ready`.

1. Send text JSON: `{"type":"audio_start","session_id":"...","mime_type":"audio/webm;codecs=opus"}`.
2. Send one complete recording as a binary WebSocket message.
3. Send text JSON: `{"type":"audio_end"}`.
4. Receive `status`, `transcript`, streaming `token`, ordered `audio`, `audio_done`, and `done` events.

Each `audio` event contains a complete base64 WAV payload and a zero-based sequence number. Recordings are capped at 8 MB and 30 seconds. The server exposes per-turn ASR, first-token, first-audio, and total timing in the final event.

## Latency evaluation

The assignment target is sub-second interaction latency. On CPU, the meaningful measurements are transcript latency, time to first token, and time to first playable audio. Results depend on the laptop, recording length, model quantization, warm/cold state, and voice model; they must be measured rather than inferred.

After starting the full stack, record a short WebM prompt and run:

```bash
python benchmarks/voice_latency.py sample.webm --runs 5
```

Run once for warm-up before recording results. Test four clients concurrently as a separate stress case. Report hardware, model tags, median, maximum, and whether each result was warm or cold.

## Failure behavior

- Unsupported or empty recordings are rejected.
- ffmpeg conversion has a 20-second timeout.
- Missing ASR/TTS packages and missing Piper models produce explicit events.
- A TTS failure does not discard the already streamed text answer.
- Audio is queued by sequence so phrases do not overlap.

