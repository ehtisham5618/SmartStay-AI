"""Offline regression tests for the final-assignment evaluation suite."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from evals.datasets import validate_datasets
from evals.metrics import percentile, precision_at_k, recall_at_k, reciprocal_rank, summarize
from evals.report import build_markdown, environment_metadata, write_reports
from evals.tool_eval import evaluate_tool_routing
from rag.retriever import RAGRetriever
from tools.crm import CRMStore


class DatasetAndMetricTests(unittest.TestCase):
    def test_required_dataset_sizes_and_sources(self):
        result = validate_datasets()
        self.assertTrue(result["ok"], result["errors"])
        self.assertGreaterEqual(result["counts"]["conversations"], 10)
        self.assertEqual(result["counts"]["rag_queries"], 30)
        self.assertGreaterEqual(result["counts"]["tool_prompts"], 20)

    def test_retrieval_metrics(self):
        retrieved = ["wrong.txt", "right.txt", "other.txt"]
        relevant = {"right.txt"}
        self.assertAlmostEqual(precision_at_k(retrieved, relevant, 3), 1 / 3)
        self.assertEqual(recall_at_k(retrieved, relevant, 3), 1.0)
        self.assertEqual(reciprocal_rank(retrieved, relevant), 0.5)

    def test_latency_summary_includes_required_statistics(self):
        result = summarize([10, 20, 30, 40, 50])
        self.assertEqual(result["median"], 30)
        self.assertEqual(result["p90"], percentile([10, 20, 30, 40, 50], 90))
        self.assertIn("p99", result)
        self.assertEqual(len(result["mean_ci95"]), 2)

    def test_retrieval_gate_separates_simple_and_policy_turns(self):
        self.assertFalse(RAGRetriever.should_retrieve("Hello, how are you?"))
        self.assertTrue(RAGRetriever.should_retrieve("What is the cancellation policy?"))


class AsyncEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_crm_full_crud(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CRMStore(Path(directory) / "test.sqlite3")
            await store.upsert("guest", name="Alice")
            self.assertEqual((await store.get("guest"))["name"], "Alice")
            await store.upsert("guest", phone="123")
            self.assertEqual((await store.get("guest"))["phone"], "123")
            self.assertTrue(await store.delete("guest"))
            self.assertIsNone(await store.get("guest"))

    async def test_annotated_tool_router(self):
        result = await evaluate_tool_routing()
        self.assertEqual(result["cases"], 24)
        self.assertGreaterEqual(result["tool_selection_accuracy"], 0.75)
        self.assertLessEqual(result["false_positive_rate"], 0.25)


class ReportTests(unittest.TestCase):
    def test_report_artifacts(self):
        report = {
            "environment": environment_metadata(),
            "datasets": {
                "counts": {"conversations": 12, "conversation_turns": 24, "rag_queries": 30, "tool_prompts": 24}
            },
            "correctness": {},
            "performance": {
                "latency": {
                    "simple": {
                        "trials": 1,
                        "error_rate": 0.0,
                        "ttft_ms": {"mean": 10, "median": 10},
                        "end_to_end_ms": {"p90": 20, "p99": 20, "median": 20},
                    }
                }
            },
            "failures": [],
        }
        self.assertIn("# SmartStay AI Evaluation Report", build_markdown(report))
        with tempfile.TemporaryDirectory() as directory:
            artifacts = write_reports(report, Path(directory))
            self.assertTrue(Path(artifacts["json"]).is_file())
            self.assertTrue(Path(artifacts["markdown"]).is_file())
            self.assertTrue(Path(artifacts["latency_graph"]).is_file())


if __name__ == "__main__":
    unittest.main()
