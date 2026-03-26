# Assignment 3 Engineering Notes

## Retrieval decisions

- Corpus: 50 hotel policy, service, room, and operations documents in `knowledge_base/`.
- Chunking: word-aware windows of 180 words with 30-word overlap.
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` on CPU.
- Store: persisted FAISS `IndexFlatIP`; vectors are L2-normalized, making inner product cosine similarity.
- Retrieval: top three results, with an in-process 128-query LRU cache.
- Prompt budget: at most three passages, each capped at 900 characters, plus the latest eight messages.
- Grounding: source filenames are placed beside passages and the model is required to cite them in square brackets.

The index is generated rather than committed. `python -m rag.build_index` refuses corpora outside the assignment's 50–100 document requirement and writes the FAISS index plus metadata under ignored `data/index/`.

## Tool orchestration decisions

All four tools have a name, description, JSON input schema, async handler, validation, timeout, and structured result. Clear intents are routed before LLM generation, then executed concurrently with retrieval. The resulting facts are inserted into the final generation prompt. This deterministic pre-generation router is more reliable on a 3B model than asking it to emit perfect JSON, while the LLM remains responsible for the guest-facing answer.

The same implementations are exposed by the official stable v1 MCP Python SDK as a stateless Streamable HTTP server. The chatbot calls the shared in-process handlers to avoid loopback latency; external MCP clients use `http://localhost:8001/mcp`.

## Realtime event order

```text
start
context { sources, tools, metrics, errors }
token { content } ...
done
```

Voice adds `transcript` before context and ordered `audio` chunks while tokens stream. Existing clients that only understand tokens remain compatible because the original event names were not changed.

## Evaluation procedure

1. Build the index and start Ollama, API, MCP server, and frontend.
2. Send one warm-up query so MiniLM, FAISS, and Qwen are resident.
3. Run `python benchmarks/rag_tools_latency.py` for preprocessing and two-user concurrency.
4. Run `python benchmarks/voice_latency.py sample.webm --runs 5` for end-to-end voice latency.
5. Record CPU, RAM, operating system, model tag, warm/cold state, average, median, p95/max, and failures.

Hardware results are not committed unless measured on the submission machine. This avoids presenting synthetic timings as benchmarks.

## Demo checklist

- Ask a policy question and point out the source badge/citation.
- Say “My name is …” and start a new session with the same browser user ID to demonstrate CRM persistence.
- Calculate a stay price and create a calendar hold.
- Ask for weather to demonstrate the external cached tool.
- Show text tokens and voice playback continuing to stream.

