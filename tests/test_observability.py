from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import observability


class ObservabilityTests(unittest.TestCase):
    def test_log_event_writes_jsonl_entry(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        original_log_path = os.environ.get("OBS_LOG_PATH")
        try:
            log_path = Path(temp_dir.name) / "events.jsonl"
            os.environ["OBS_LOG_PATH"] = str(log_path)

            observability.log_event(
                "chat_complete",
                question="What programs are offered?",
                elapsed_ms=1234,
                slow=False,
            )

            events = observability.read_events(log_path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "chat_complete")
            self.assertEqual(events[0]["question"], "What programs are offered?")
        finally:
            if original_log_path is None:
                os.environ.pop("OBS_LOG_PATH", None)
            else:
                os.environ["OBS_LOG_PATH"] = original_log_path
            temp_dir.cleanup()

    def test_summarize_events_reports_failures_and_slow_questions(self) -> None:
        summary = observability.summarize_events(
            [
                {
                    "event": "chat_complete",
                    "question": "What programs are offered at DIU?",
                    "elapsed_ms": 6200,
                },
                {
                    "event": "chat_complete",
                    "question": "What programs are offered at DIU?",
                    "elapsed_ms": 7100,
                },
                {
                    "event": "retrieval_miss",
                    "question": "What is the admission deadline?",
                    "ts": "2026-04-28T00:00:00+00:00",
                },
                {
                    "event": "chat_empty_stream",
                    "question": "What is the admission deadline?",
                    "ts": "2026-04-28T00:01:00+00:00",
                },
            ],
            slow_request_ms=5000,
            top_n=3,
        )

        self.assertEqual(summary["event_counts"]["chat_complete"], 2)
        self.assertEqual(summary["top_failed_questions"][0]["question"], "what is the admission deadline?")
        self.assertEqual(summary["top_failed_questions"][0]["count"], 2)
        self.assertEqual(summary["top_slow_questions"][0]["question"], "what programs are offered at diu?")
        self.assertEqual(summary["top_slow_questions"][0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
