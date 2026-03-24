import asyncio
import subprocess
import unittest
from unittest.mock import patch

from backend.app.voice_pipeline import AudioConverter, audio_extension, should_flush_sentence


class VoiceProtocolTests(unittest.TestCase):
    def test_browser_mime_types_map_to_safe_extensions(self):
        self.assertEqual(audio_extension("audio/webm;codecs=opus"), "webm")
        self.assertEqual(audio_extension("audio/ogg"), "ogg")
        self.assertEqual(audio_extension("application/octet-stream"), "webm")

    def test_sentence_flushing_balances_latency_and_natural_speech(self):
        self.assertFalse(should_flush_sentence("Short"))
        self.assertTrue(should_flush_sentence("Your room is ready."))
        self.assertTrue(should_flush_sentence("This opening phrase is long enough, ", first_fragment=True))


class ConverterTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_audio_is_rejected_before_ffmpeg(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            await AudioConverter().to_wav_16k(b"")

    async def test_unsupported_extension_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            await AudioConverter().to_wav_16k(b"audio", "exe")

    async def test_ffmpeg_timeout_has_clear_failure(self):
        with patch(
            "backend.app.voice_pipeline.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 20),
        ):
            with self.assertRaisesRegex(RuntimeError, "exceeded"):
                await AudioConverter().to_wav_16k(b"not-empty", "webm")


if __name__ == "__main__":
    unittest.main()

