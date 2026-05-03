from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.gemini import GeminiGroundedResponder


class StubGeminiResponder(GeminiGroundedResponder):
    def __init__(self, *, failures: set[str] | None = None, failure_error: Exception | None = None) -> None:
        super().__init__(api_key="test-key", model="primary-model")
        self.model_candidates = ["primary-model"]
        self.failures = failures or set()
        self.failure_error = failure_error

    def _generate_with_model(self, payload: dict, model: str, api_key: str | None = None) -> dict:
        if model in self.failures:
            if self.failure_error:
                raise self.failure_error
            raise RuntimeError("HTTP 503 temporary unavailable")
        self.last_error = ""
        self.last_successful_model = model
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Stub answer"}],
                    },
                }
            ],
        }


class GeminiGroundedResponderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.responder = GeminiGroundedResponder(api_key="test-key")

    def test_clean_text_returns_raw_string(self) -> None:
        raw = (
            "Hello! I'd be happy to help you with information about DIU. "
            "Based on the provided information, the general admission requirements are available online."
        )

        cleaned = self.responder._clean_text(raw)

        self.assertEqual(
            cleaned,
            raw,
        )

    def test_build_prompt_requests_natural_assistant_voice(self) -> None:
        match = SimpleNamespace(
            chunk=SimpleNamespace(
                title="Admission Information",
                url="https://daffodilvarsity.edu.bd/admission",
                text="Applicants can explore the admission portal for current requirements.",
            )
        )

        prompt = self.responder._build_prompt(
            user_question="Tell me about DIU admission requirements",
            matches=[match],
            language="en",
        )

        self.assertIn("Return only the answer body", prompt)
        self.assertIn("AGENT ROLE: GENERAL FAQ ASSISTANT.", prompt)
        self.assertIn("Admission Information", prompt)
        self.assertIn("https://daffodilvarsity.edu.bd/admission", prompt)
        self.assertNotIn("exactly one fenced ```html block", prompt)

    def test_freeform_prompt_includes_recent_session_context_for_followups(self) -> None:
        prompt = self.responder._build_freeform_prompt(
            user_question="what about that for jobs?",
            language="en",
            chat_history=[
                {"role": "user", "mode": "project1", "content": "Tell me about game development"},
                {"role": "assistant", "mode": "project1", "content": "Game development combines programming, art, level design, and testing."},
            ],
        )

        self.assertIn("AGENT ROLE: GENERAL FAQ ASSISTANT.", prompt)
        self.assertNotIn("Recent session context", prompt)
        self.assertNotIn("assistant [project1]", prompt)

    def test_specialist_canvas_instruction_only_appears_when_prompt_requests_it(self) -> None:
        prompt = self.responder._build_freeform_prompt(
            user_question=(
                "Answer in DIU Scholarship Mode. Focus on DIU scholarships and waivers. "
                "For every substantive scholarship answer, include the normal chat answer plus a green DIU Canvas companion without waiting for the user to ask for visualization.\n\n"
                "User question: What scholarship opportunities are available at DIU?"
            ),
            language="en",
        )

        self.assertIn("CRITICAL OVERRIDE: You are now a senior frontend developer", prompt)
        self.assertIn("exactly one ```html block", prompt.lower())

    def test_system_instruction_forbids_canned_faq_replay(self) -> None:
        instruction = self.responder._build_system_instruction()

        self.assertIn("SYSTEM: DIU Helpful Assistant Mode", instruction)
        self.assertIn("You are the official DIU Assistant", instruction)
        self.assertIn("clean, structured Markdown", instruction)
        self.assertNotIn("powered by Gemini", instruction)

    def test_clean_text_removes_gemini_identity_intro(self) -> None:
        raw = "I am Gemini, the Google AI model. Here is the admission answer."

        cleaned = self.responder._sanitize_identity_leaks(raw)

        self.assertNotIn("Gemini", cleaned)
        self.assertNotIn("Google AI model", cleaned)
        self.assertIn("DIU Assistant", cleaned)

    def test_clean_text_removes_powered_by_gemini_phrase(self) -> None:
        raw = (
            "I am DIU Assistant, designed to help with DIU information, "
            "drawing on official resources and my capabilities powered by Gemini."
        )

        cleaned = self.responder._sanitize_identity_leaks(raw)

        self.assertNotIn("powered by Gemini", cleaned)
        self.assertNotIn("Gemini", cleaned)

    def test_records_successful_primary_model(self) -> None:
        responder = StubGeminiResponder()

        answer = responder.answer_freeform(user_question="Hello", language="en")

        self.assertEqual(answer, "Stub answer")
        self.assertEqual(responder.last_successful_model, "primary-model")

    def test_default_model_candidates_include_primary_then_25_flash_fallback(self) -> None:
        responder = GeminiGroundedResponder(api_key="test-key", model="gemini-1.5-flash")

        self.assertEqual(
            responder.model_candidates,
            ["gemini-1.5-flash", "gemini-2.5-flash"],
        )

    def test_key_rotation_keeps_primary_model(self) -> None:
        responder = StubGeminiResponder(failures={"primary-model"})
        responder.api_keys = ["bad-key", "good-key"]
        used_attempts: list[tuple[str | None, str]] = []

        def fake_generate(payload: dict, model: str, api_key: str | None = None) -> dict:
            used_attempts.append((api_key, model))
            if api_key == "bad-key":
                raise RuntimeError("HTTP 429 quota exceeded")
            responder.last_error = ""
            responder.last_successful_model = model
            return {"candidates": [{"content": {"parts": [{"text": "Stub answer"}]}}]}

        responder._generate_with_model = fake_generate  # type: ignore[method-assign]

        answer = responder.answer_freeform(user_question="Hello", language="en")

        self.assertEqual(answer, "Stub answer")
        self.assertEqual(responder.last_successful_model, "primary-model")
        # Ensure that it tried bad-key and good-key. The exact number depends on retry variants.
        self.assertIn(("bad-key", "primary-model"), used_attempts)
        self.assertIn(("good-key", "primary-model"), used_attempts)

    def test_uses_next_api_key_when_first_key_fails(self) -> None:
        class RotatingKeyResponder(GeminiGroundedResponder):
            def __init__(self) -> None:
                super().__init__(api_key="bad-key", model="primary-model")
                self.api_keys = ["bad-key", "good-key"]
                self.model_candidates = ["primary-model"]
                self.used_keys: list[str | None] = []

            def _generate_with_model(self, payload: dict, model: str, api_key: str | None = None) -> dict:
                self.used_keys.append(api_key)
                if api_key == "bad-key":
                    raise RuntimeError("HTTP 429 quota exceeded")
                self.last_error = ""
                self.last_successful_model = model
                return {"candidates": [{"content": {"parts": [{"text": "Rotated answer"}]}}]}

        responder = RotatingKeyResponder()

        answer = responder.answer_freeform(user_question="Hello", language="en")

        self.assertEqual(answer, "Rotated answer")
        self.assertIn("bad-key", responder.used_keys)
        self.assertIn("good-key", responder.used_keys)

    def test_timeout_error_uses_next_api_key(self) -> None:
        responder = StubGeminiResponder(
            failures={"primary-model"},
            failure_error=TimeoutError("timed out"),
        )
        responder.api_keys = ["slow-key", "good-key"]
        used_attempts: list[tuple[str | None, str]] = []

        def fake_generate(payload: dict, model: str, api_key: str | None = None) -> dict:
            used_attempts.append((api_key, model))
            if api_key == "slow-key":
                raise TimeoutError("timed out")
            responder.last_error = ""
            responder.last_successful_model = model
            return {"candidates": [{"content": {"parts": [{"text": "Stub answer"}]}}]}

        responder._generate_with_model = fake_generate  # type: ignore[method-assign]

        answer = responder.answer_freeform(user_question="Hello", language="en")

        self.assertEqual(answer, "Stub answer")
        self.assertEqual(responder.last_successful_model, "primary-model")
        self.assertIn(("slow-key", "primary-model"), used_attempts)
        self.assertIn(("good-key", "primary-model"), used_attempts)

    def test_fallback_model_is_used_only_after_primary_exhausts_all_keys(self) -> None:
        responder = StubGeminiResponder()
        responder.api_keys = ["key-a", "key-b"]
        responder.model_candidates = ["primary-model", "fallback-model"]
        used_attempts: list[tuple[str | None, str]] = []

        def fake_generate(payload: dict, model: str, api_key: str | None = None) -> dict:
            used_attempts.append((api_key, model))
            if model == "primary-model":
                raise RuntimeError("HTTP 429 quota exceeded")
            responder.last_error = ""
            responder.last_successful_model = model
            return {"candidates": [{"content": {"parts": [{"text": "Fallback answer"}]}}]}

        responder._generate_with_model = fake_generate  # type: ignore[method-assign]

        answer = responder.answer_freeform(user_question="Hello", language="en")

        self.assertEqual(answer, "Fallback answer")
        self.assertEqual(responder.last_successful_model, "fallback-model")
        self.assertIn(("key-a", "primary-model"), used_attempts)
        self.assertIn(("key-b", "primary-model"), used_attempts)
        self.assertIn(("key-a", "fallback-model"), used_attempts)

    def test_clean_text_preserves_auto_generated_tail_sections(self) -> None:
        raw = (
            "DIU offers several waiver categories.\n\n"
            "**What you should do next**\n"
            "1. Check the office.\n\n"
            "Would you like me to turn this into a checklist?"
        )

        cleaned = self.responder._clean_text(raw)

        self.assertEqual(cleaned, raw)

    def test_google_search_tool_can_be_disabled_explicitly(self) -> None:
        payload: dict = {}
        self.responder.enable_google_search = False

        self.responder._add_google_search_tool(payload)

        self.assertNotIn("tools", payload)

    def test_context_answers_use_standard_document_token_budget(self) -> None:
        responder = StubGeminiResponder()
        captured: dict = {}

        def fake_generate(payload: dict, model: str, api_key: str | None = None) -> dict:
            captured["payload"] = payload
            responder.last_error = ""
            responder.last_successful_model = model
            return {"candidates": [{"content": {"parts": [{"text": "Stub answer"}]}}]}

        responder._generate_with_model = fake_generate  # type: ignore[method-assign]

        responder.answer_from_context(
            user_question="Tell me about DIU admission requirements",
            matches=[SimpleNamespace(chunk=SimpleNamespace(title="Admission", url="https://daffodilvarsity.edu.bd/admission", text="Admission details"))],
            language="en",
            enable_search=False,
        )

        generation_config = captured["payload"]["generationConfig"]
        self.assertEqual(generation_config["maxOutputTokens"], responder.document_max_output_tokens)
        self.assertNotIn("tools", captured["payload"])

    def test_freeform_answers_can_enable_google_search_when_requested(self) -> None:
        responder = StubGeminiResponder()
        captured: dict = {}

        def fake_generate(payload: dict, model: str, api_key: str | None = None) -> dict:
            captured["payload"] = payload
            responder.last_error = ""
            responder.last_successful_model = model
            return {"candidates": [{"content": {"parts": [{"text": "Stub answer"}]}}]}

        responder._generate_with_model = fake_generate  # type: ignore[method-assign]

        responder.answer_freeform(
            user_question="What are the latest DIU notices?",
            language="en",
            enable_search=True,
        )

        self.assertEqual(
            captured["payload"]["generationConfig"]["maxOutputTokens"],
            responder.standard_max_output_tokens,
        )
        self.assertEqual(captured["payload"]["tools"], [{"google_search": {}}])

    def test_detects_truncated_stream_payloads_from_finish_reason(self) -> None:
        payload = {
            "candidates": [
                {
                    "finishReason": "MAX_TOKENS",
                    "content": {"parts": [{"text": "Partial answer"}]},
                }
            ]
        }

        self.assertTrue(self.responder._payload_truncated(payload))

    def test_context_excerpt_uses_full_text_when_limit_disabled(self) -> None:
        responder = GeminiGroundedResponder(api_key="test-key")
        responder.context_chars = 0
        text = "A" * 5000

        excerpt = responder._context_excerpt(text)

        self.assertEqual(excerpt, text)

    def test_remembers_grounding_sources_from_gemini_metadata(self) -> None:
        payload = {
            "candidates": [
                {
                    "groundingMetadata": {
                        "groundingChunks": [
                            {
                                "web": {
                                    "uri": "https://daffodilvarsity.edu.bd/admission",
                                    "title": "Admission",
                                }
                            },
                            {
                                "web": {
                                    "uri": "https://daffodilvarsity.edu.bd/admission",
                                    "title": "Duplicate",
                                }
                            },
                            {
                                "web": {
                                    "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/example",
                                    "title": "scribd.com",
                                }
                            },
                        ]
                    }
                }
            ]
        }

        self.responder._remember_grounding_sources(payload)

        self.assertEqual(
            self.responder.last_grounding_sources,
            ["https://daffodilvarsity.edu.bd/admission", "https://vertexaisearch.cloud.google.com/grounding-api-redirect/example"],
        )
        self.assertEqual(self.responder.last_grounding_titles, ["Admission", "scribd.com"])


if __name__ == "__main__":
    unittest.main()
