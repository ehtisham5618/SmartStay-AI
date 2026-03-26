# Evaluation Methodology

This document is the stable methodology record for SmartStay AI's final assignment. Generated measurements belong in `eval_reports/` and must be produced on the submission machine; they are intentionally excluded from version control so old hardware results cannot be mistaken for current evidence.

## Scope and datasets

The suite evaluates the current text pipeline, including conversation memory, policy controls, RAG, CRM, calculator, calendar, and weather routing. Voice component latency remains covered by `benchmarks/voice_latency.py`, while the final suite instruments the common conversation path used after transcription.

- `conversations.json`: 12 annotated multi-turn dialogues with 24 total turns.
- `rag_ground_truth.json`: 30 policy questions, relevant source filenames, and answer terms. The same 30 responses are checked for faithfulness.
- `tool_invocations.json`: 24 positive and negative tool-routing prompts.
- `knowledge_base/`: 50 hotel-domain source documents.

Dataset annotations are committed so every run uses the same ground truth. Cases cover normal requests, follow-up memory, safe refusal, invalid tool inputs, and prompts that must not call a tool.

## Correctness metrics

For retrieved list `R_k` and annotated relevant set `G`:

```text
precision@k = |R_k intersection G| / k
recall@k    = |R_k intersection G| / |G|
MRR         = mean(1 / rank of first relevant result)
```

Context relevance is precision@3 against the annotated filename. Answer-term coverage checks expected domain facts. Citation rate checks whether the streamed answer contains an annotated `[source.txt]` citation.

Faithfulness is a transparent lexical heuristic: split an answer into claims and mark a claim supported when at least 45% of its non-stopword content tokens occur in the retrieved passages. The report averages supported claims across all 30 QA pairs. This conservative proxy is reproducible and dependency-free, but paraphrases can produce false negatives; all low-scoring records require human review.

Dialogue task completion requires every annotated content, source, tool, and refusal expectation to pass. Policy adherence checks that out-of-domain requests receive the hotel-domain boundary and valid requests are not spuriously refused. Coherence measures whether annotated facts introduced earlier reappear correctly in later turns.

Tool invocation accuracy compares selected tool names and arguments with ground truth. False-positive rate is reported separately over negative examples. Functional checks exercise CRM create/read/update/delete, valid and invalid calculator requests, calendar file generation and validation, and weather validation. The successful weather call is opt-in because it requires network access.

## Performance metrics

The default suite executes 30 trials for each scenario:

1. simple conversation;
2. RAG-only hotel-policy question;
3. tool-only deterministic price request;
4. mixed RAG and tool request.

Time to first token (TTFT) runs from client send to the first `token` WebSocket event. Inter-token latency is the arithmetic mean of adjacent token arrival gaps. End-to-end latency runs from client send through the `done` event. Each metric reports count, mean, median, p90, p99, minimum, maximum, and a normal-approximation 95% confidence interval around the mean.

The concurrency test steps through 1, 2, 4, 6, and 8 simulated users. Each maintains an independent session and sends three sequential turns while users run concurrently. It reports completed turns per second, errors, and latency. A level is sustainable when error rate is at most 5%, median TTFT is at most 2 seconds, and median end-to-end latency is at most 10 seconds. These thresholds can be overridden with environment variables and should be justified if changed.

## Reproduction

Start the API and local Ollama model, then run:

```bash
python evaluate.py
```

Use `python evaluate.py --quick` only for smoke testing. The full command creates `eval_reports/evaluation.json`, `eval_reports/evaluation.md`, and `eval_reports/latency.svg`. Preserve the full generated directory with the assignment submission or copy verified measurements into the README results table.

## Interpretation rules

- Never compare latency runs from different hardware without reporting both environments.
- Treat p90/p99 and failure records as more informative than a mean alone.
- A zero or missing live metric means the API was unavailable or the scenario failed; it is not a successful result.
- Inspect individual retrieval misses before changing `top_k`; larger values may improve recall while harming precision and prompt budget.
- Inspect negative routing cases before broadening keyword patterns, because broader matching can increase false positives.
- Repeat the full run after changes to prompts, knowledge documents, models, quantization, or orchestration.
