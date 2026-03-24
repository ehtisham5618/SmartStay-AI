import asyncio
import unittest

from conversation.memory_manager import MemoryManager
from conversation.prompt_builder import PromptBuilder
from conversation.session_manager import SessionManager


class FakeLLM:
    async def generate_stream(self, prompt):
        for token in ("Local ", "response"):
            await asyncio.sleep(0)
            yield token


class MemoryAndPromptTests(unittest.TestCase):
    def test_memory_is_bounded_and_isolated(self):
        memory = MemoryManager(max_messages=2)
        for content in ("one", "two", "three"):
            memory.add_message("a", "user", content)
        memory.add_message("b", "user", "separate")

        self.assertEqual([item["content"] for item in memory.get_history("a")], ["two", "three"])
        self.assertEqual(memory.get_history("b")[0]["content"], "separate")

    def test_prompt_contains_policy_history_and_current_turn(self):
        prompt = PromptBuilder().build_prompt(
            [{"role": "user", "content": "I need a Deluxe room"}],
            "It is for two guests",
        )

        self.assertIn("Only discuss hotel", prompt)
        self.assertIn("I need a Deluxe room", prompt)
        self.assertIn("It is for two guests", prompt)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_turn_session_retains_dialogue(self):
        memory = MemoryManager()
        sessions = SessionManager(FakeLLM(), memory, PromptBuilder())
        session_id = sessions.create_session()

        response = await sessions.process_message(session_id, "What time is check-in?")

        self.assertEqual(response, "Local response")
        self.assertEqual(
            memory.get_history(session_id),
            [
                {"role": "user", "content": "What time is check-in?"},
                {"role": "assistant", "content": "Local response"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
