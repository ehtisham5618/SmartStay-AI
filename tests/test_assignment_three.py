import asyncio
import tempfile
import unittest
from pathlib import Path

from conversation.prompt_builder import PromptBuilder
from rag.build_index import collect_chunks
from rag.chunker import chunk_text
from rag.retriever import RAGRetriever
from tools.calculator import calculate_room_cost
from tools.crm import CRMStore
from tools.orchestrator import ToolOrchestrator
from tools.registry import ToolRegistry


class CorpusAndRetrievalTests(unittest.TestCase):
    def test_repository_contains_required_document_count(self):
        chunks, metadata = collect_chunks()
        sources = {item["source"] for item in metadata}
        self.assertEqual(len(sources), 50)
        self.assertEqual(len(chunks), len(metadata))

    def test_chunks_overlap_without_exceeding_word_budget(self):
        words = [f"word{i}" for i in range(260)]
        chunks = chunk_text(" ".join(words), chunk_words=100, overlap_words=20)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertLessEqual(max(len(chunk.split()) for chunk in chunks), 100)
        self.assertEqual(chunks[0].split()[-20:], chunks[1].split()[:20])

    def test_retrieval_cache_avoids_reembedding(self):
        calls = {"embed": 0, "search": 0}

        def embed(query):
            calls["embed"] += 1
            return [1.0]

        def search(vector, top_k):
            calls["search"] += 1
            return [{"text": "Policy", "source": "policy.txt", "score": 0.9}]

        retriever = RAGRetriever(embed_query=embed, search=search)
        self.assertEqual(retriever.retrieve("Cancellation policy"), retriever.retrieve(" cancellation  policy "))
        self.assertEqual(calls, {"embed": 1, "search": 1})

    def test_prompt_includes_citable_source_and_tool_result(self):
        prompt = PromptBuilder().build_prompt(
            [],
            "Can I cancel?",
            [{"source": "cancellation_policy.txt", "text": "Cancel 48 hours before arrival."}],
            [{"name": "crm_profile", "ok": True, "output": {"found": True}}],
        )
        self.assertIn("[cancellation_policy.txt]", prompt)
        self.assertIn("TOOL RESULTS", prompt)


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_calculator_is_deterministic(self):
        result = await calculate_room_cost("Deluxe", "2026-05-01", "2026-05-04", 2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["total_usd"], 450.0)

    async def test_crm_persists_across_store_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crm.sqlite3"
            first = CRMStore(path)
            await first.upsert("guest-1", name="Ali", preference="quiet room")
            second = CRMStore(path)
            profile = await second.get("guest-1")
            self.assertEqual(profile["name"], "Ali")
            self.assertIn("quiet room", profile["preferences"])

    async def test_registry_rejects_unknown_arguments(self):
        registry = ToolRegistry()

        async def handler(value):
            return {"ok": True, "value": value}

        registry.register(
            {
                "name": "demo",
                "description": "demo",
                "input_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
            handler,
        )
        result = await registry.execute("demo", {"value": "ok", "extra": True})
        self.assertFalse(result.ok)
        self.assertIn("Unknown arguments", result.output["error"])

    async def test_orchestrator_can_plan_multiple_tools(self):
        calls = ToolOrchestrator().plan(
            "Calculate a Deluxe room from 2026-05-01 to 2026-05-03 and show weather in Islamabad on 2026-05-01",
            "guest-1",
        )
        names = {name for name, _ in calls}
        self.assertIn("calculate_room_cost", names)
        self.assertIn("get_weather", names)


if __name__ == "__main__":
    unittest.main()

