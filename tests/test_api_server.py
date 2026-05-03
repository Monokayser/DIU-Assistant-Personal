from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.main as api_server
from backend.main import format_backend_error
from src.apps.canvas.services.artifacts import resolve_artifact_path
from src.core.knowledge import DIUCampusChatbot
from src.core.config import origin_is_allowed


class ApiServerErrorFormattingTests(unittest.TestCase):
    def test_origin_policy_allows_localhost(self) -> None:
        patterns = [
            "http://localhost:5173",
        ]

        self.assertTrue(origin_is_allowed("http://localhost:5173", patterns))
        self.assertTrue(origin_is_allowed("http://localhost:5173", patterns))

    def test_origin_policy_rejects_unknown_hosts(self) -> None:
        patterns = [
            "http://localhost:5173",
        ]

        self.assertFalse(origin_is_allowed("https://evil.example.com", patterns))

    def test_server_address_defaults_to_localhost(self) -> None:
        original_host = os.environ.get("API_HOST")
        original_port = os.environ.get("API_PORT")
        try:
            os.environ.pop("API_HOST", None)
            os.environ.pop("API_PORT", None)
            self.assertEqual(api_server.get_server_address(), ("127.0.0.1", 8765))
        finally:
            if original_host is None:
                os.environ.pop("API_HOST", None)
            else:
                os.environ["API_HOST"] = original_host
            if original_port is None:
                os.environ.pop("API_PORT", None)
            else:
                os.environ["API_PORT"] = original_port

    def test_server_url_prints_local_loopback_for_wildcard_bind(self) -> None:
        self.assertEqual(api_server.format_server_url("0.0.0.0", 8765), "http://127.0.0.1:8765")

    def test_invalid_key_error_is_user_facing(self) -> None:
        message = format_backend_error(RuntimeError("API_KEY_INVALID: API key not valid"))

        self.assertIn("could not authenticate with the current API key", message)

    def test_quota_error_is_user_facing(self) -> None:
        message = format_backend_error(RuntimeError("quota exceeded, check billing"))

        self.assertIn("quota", message)

    def test_quota_error_uses_retry_delay_when_available(self) -> None:
        message = format_backend_error(RuntimeError('HTTP 429 {"error":{"details":[{"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"11s"}]}}'))

        self.assertIn("11 seconds", message)

    def test_daily_free_tier_quota_error_mentions_project_model_limit(self) -> None:
        message = format_backend_error(
            RuntimeError(
                "Quota exceeded for metric: generativelanguage.googleapis.com/"
                "generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash-lite "
                "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
            )
        )

        self.assertIn("free daily usage limit", message)
        self.assertIn("current project", message)

    def test_high_demand_error_is_user_facing(self) -> None:
        message = format_backend_error(RuntimeError("HTTP 503 high demand unavailable"))

        self.assertIn("high demand", message)

    def test_upload_endpoint_extracts_text_when_supabase_is_not_configured(self) -> None:
        payload = {
            "session_id": "test-upload",
            "return_text": True,
            "files": [
                {
                    "filename": "daily-notes.txt",
                    "content_base64": "QWRtaXNzaW9uIGZpbGUgY29udGVudA==",
                }
            ],
        }

        result = api_server.handle_upload(payload)

        self.assertTrue(result["ok"])
        self.assertEqual(result["files"][0]["filename"], "daily-notes.txt")
        self.assertIn("Admission file content", result["files"][0]["text"])

    def test_uploaded_text_file_can_be_answered_later_without_supabase(self) -> None:
        original_client = api_server.AI_CLIENT

        class FakeClient:
            is_configured = True

            def answer_from_context(self, **kwargs):
                matches = kwargs.get("matches") or []
                return matches[0].chunk.text if matches else "LLM answer"

            def answer_freeform(self, **kwargs):
                return "LLM freeform answer"

        session_id = "test-upload-later"
        upload_payload = {
            "session_id": session_id,
            "return_text": True,
            "files": [
                {
                    "filename": "later-note.txt",
                    "content_base64": (
                        "RGl1IGRvY3VtZW50IG5vdGUKQWRtaXNzaW9uIHJlcXVpcmVzIEhTQyBvciBlcXVpdmFsZW50LgpI"
                        "ZWxwIGRlc2sgbnVtYmVyOiArODgwMTIzNDU2Nzg5Lg=="
                    ),
                }
            ],
        }

        api_server.AI_CLIENT = FakeClient()  # type: ignore[assignment]
        try:
            upload_result = api_server.handle_upload(upload_payload)
            answer_result = api_server.answer_from_document_rag(
                "Summarize the uploaded document and mention the help desk number.",
                [],
                [],
                session_id,
                attached_files=["later-note.txt"],
            )
        finally:
            api_server.AI_CLIENT = original_client

        self.assertTrue(upload_result["ok"])
        self.assertTrue(upload_result["files"][0]["stored"])
        self.assertGreater(upload_result["files"][0]["chunks"], 0)
        self.assertTrue(answer_result["found_match"])
        self.assertTrue(
            any((source.get("source") or "") == "later-note.txt" for source in answer_result["sources"])
        )

    def test_uploaded_text_file_summary_uses_remembered_context_when_retrieval_falls_back(self) -> None:
        original_client = api_server.AI_CLIENT

        class FakeClient:
            is_configured = True

            def answer_from_context(self, **kwargs):
                matches = kwargs.get("matches") or []
                return matches[0].chunk.text if matches else "LLM answer"

            def answer_freeform(self, **kwargs):
                return "LLM freeform answer"

        session_id = "test-upload-summary"
        upload_payload = {
            "session_id": session_id,
            "return_text": True,
            "files": [
                {
                    "filename": "note.txt",
                    "content_base64": "SGVsbG8gRElVLiBTY2hvbGFyc2hpcCBpbmZvIGhlcmUu",
                }
            ],
        }

        api_server.AI_CLIENT = FakeClient()  # type: ignore[assignment]
        try:
            upload_result = api_server.handle_upload(upload_payload)
            answer_result = api_server.answer_from_document_rag(
                "Summarize the uploaded file",
                [],
                [],
                session_id,
                attached_files=["note.txt"],
            )
        finally:
            api_server.AI_CLIENT = original_client

        self.assertTrue(upload_result["ok"])
        self.assertTrue(answer_result["found_match"])
        self.assertNotIn("do not have readable text", answer_result["answer"].lower())
        self.assertTrue(
            any((source.get("source") or "") == "note.txt" for source in answer_result["sources"])
        )

    def test_uploaded_context_returns_error_when_model_fails(self) -> None:
        original_client = api_server.AI_CLIENT

        class FailingClient:
            is_configured = True

            def answer_from_context(self, **kwargs):
                raise RuntimeError("quota exceeded, check billing")

            def answer_freeform(self, **kwargs):
                raise RuntimeError("quota exceeded, check billing")

        api_server.AI_CLIENT = FailingClient()  # type: ignore[assignment]
        try:
            result = api_server.answer_from_uploaded_context(
                "Summarize the uploaded file",
                [],
                [{"title": "Note", "source": "note.txt", "url": "note.txt", "content": "Important uploaded text"}],
                attached_files=["note.txt"],
            )
        finally:
            api_server.AI_CLIENT = original_client

        self.assertIn("error", result)
        self.assertIn("quota", result["error"].lower())

    def test_upload_endpoint_uses_gemini_when_parser_cannot_extract_file(self) -> None:
        original_client = api_server.AI_CLIENT

        class FakeClient:
            is_configured = True

            def extract_upload_text(self, *, file_bytes: bytes, filename: str, mime_type: str | None = None) -> str:
                return "Extracted image or scanned PDF text"

        api_server.AI_CLIENT = FakeClient()  # type: ignore[assignment]
        try:
            result = api_server.handle_upload(
                {
                    "session_id": "test-vision-upload",
                    "return_text": True,
                    "files": [
                        {
                            "filename": "notice.png",
                            "mime_type": "image/png",
                            "content_base64": "AA==",
                        }
                    ],
                }
            )
        finally:
            api_server.AI_CLIENT = original_client

        self.assertTrue(result["ok"])
        self.assertEqual(result["files"][0]["extracted_with"], "gemini")
        self.assertIn("Extracted image", result["files"][0]["text"])

    def test_direct_upload_answer_sends_file_bytes_to_gemini(self) -> None:
        original_client = api_server.AI_CLIENT

        class FakeClient:
            is_configured = True

            def answer_with_uploads(self, *, user_question, uploads, language, chat_history=None, assistant_mode=False):
                self.uploads = uploads
                self.chat_history = chat_history
                self.assistant_mode = assistant_mode
                return f"Direct answer for {uploads[0]['filename']}"

        fake_client = FakeClient()
        api_server.AI_CLIENT = fake_client  # type: ignore[assignment]
        try:
            result = api_server.answer_from_direct_uploads(
                "Summarize the uploaded PDF",
                [],
                [
                    {
                        "filename": "scan.pdf",
                        "mime_type": "application/pdf",
                        "file_bytes": b"%PDF-scanned",
                    }
                ],
            )
        finally:
            api_server.AI_CLIENT = original_client

        self.assertTrue(result["found_match"])
        self.assertTrue(result["used_model"])
        self.assertIn("Direct answer", result["answer"])
        self.assertEqual(fake_client.uploads[0]["file_bytes"], b"%PDF-scanned")
        self.assertEqual(fake_client.chat_history, [])
        self.assertTrue(fake_client.assistant_mode)
        self.assertFalse(result["artifacts"])

    def test_direct_upload_answer_creates_canvas_without_extra_lens(self) -> None:
        original_client = api_server.AI_CLIENT
        original_artifact_dir = api_server.CANVAS_ARTIFACTS_DIR
        temp_dir = tempfile.TemporaryDirectory()

        class FakeClient:
            is_configured = True

            def answer_with_uploads(self, *, user_question, uploads, language, chat_history=None, assistant_mode=False):
                self.user_question = user_question
                self.chat_history = chat_history
                self.assistant_mode = assistant_mode
                return "Course-focused direct upload answer"

        fake_client = FakeClient()
        api_server.AI_CLIENT = fake_client  # type: ignore[assignment]
        api_server.CANVAS_ARTIFACTS_DIR = Path(temp_dir.name)
        try:
            result = api_server.answer_from_direct_uploads(
                "Summarize this file",
                [],
                [
                    {
                        "filename": "catalog.pdf",
                        "mime_type": "application/pdf",
                        "file_bytes": b"%PDF-catalog",
                    }
                ],
                session_id="course-upload-canvas-test",
                mode="course",
            )
        finally:
            api_server.AI_CLIENT = original_client
            api_server.CANVAS_ARTIFACTS_DIR = original_artifact_dir
            temp_dir.cleanup()

        self.assertEqual(fake_client.user_question, "Summarize this file")
        self.assertEqual(fake_client.chat_history, [])
        self.assertFalse(fake_client.assistant_mode)
        self.assertTrue(result["artifacts"])
        self.assertTrue(any(item["mime_type"] == "text/html" for item in result["artifacts"]))

    def test_greeting_ignores_stale_history(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        temp_dir = tempfile.TemporaryDirectory()

        class EchoGeminiClient:
            is_configured = True
            last_error = ""

            def answer_freeform(self, **kwargs):
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                return "Gemini generated answer"

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 2},
                "chunks": [
                    {
                        "id": "course-0",
                        "url": "https://daffodilvarsity.edu.bd/programs",
                        "title": "Programs",
                        "text": "DIU offers program and course information.",
                    },
                    {
                        "id": "scholarship-0",
                        "url": "https://daffodilvarsity.edu.bd/scholarship",
                        "title": "Scholarships",
                        "text": "DIU offers scholarships and waivers.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=EchoGeminiClient(),
                auto_sync=False,
            )

            result = api_server.answer_from_university_knowledge(
                "hello",
                [
                    {"role": "user", "content": "What scholarship opportunities are available at DIU?"},
                    {"role": "assistant", "content": "DIU offers scholarships and waivers."},
                ],
                "hello-canvas-test",
                [],
                "assistant",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            temp_dir.cleanup()

        self.assertTrue(result["found_match"])
        self.assertTrue(result["used_model"])
        self.assertFalse(result["sources"])
        self.assertEqual(result["answer"], "Gemini generated answer")

    def test_clarification_turn_ignores_stale_history(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        temp_dir = tempfile.TemporaryDirectory()

        class EchoGeminiClient:
            is_configured = True
            last_error = ""

            def answer_freeform(self, **kwargs):
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                return "Gemini generated answer"

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 2},
                "chunks": [
                    {
                        "id": "admission-0",
                        "url": "https://daffodilvarsity.edu.bd/admission",
                        "title": "Admission",
                        "text": "DIU admission information and eligibility guidance.",
                    },
                    {
                        "id": "scholarship-0",
                        "url": "https://daffodilvarsity.edu.bd/scholarship",
                        "title": "Scholarships",
                        "text": "DIU scholarships and waivers.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=EchoGeminiClient(),
                auto_sync=False,
            )

            result = api_server.answer_from_university_knowledge(
                "huh?",
                [
                    {"role": "user", "content": "If I fail HSC, can I admit myself into DIU?"},
                    {"role": "assistant", "content": "Admission eligibility depends on official requirements."},
                ],
                "clarification-canvas-test",
                [],
                "assistant",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            temp_dir.cleanup()

        self.assertTrue(result["found_match"])
        self.assertTrue(result["used_model"])
        self.assertFalse(result["sources"])
        self.assertEqual(result["answer"], "Gemini generated answer")
        self.assertNotIn("hsc", result["answer"].lower())

    def test_document_rag_falls_back_to_frontend_context_without_supabase(self) -> None:
        original_client = api_server.AI_CLIENT

        class FakeClient:
            is_configured = True

            def answer_from_context(self, **kwargs):
                matches = kwargs.get("matches") or []
                return matches[0].chunk.text if matches else "LLM answer"

            def answer_freeform(self, **kwargs):
                return "LLM freeform answer"

        api_server.AI_CLIENT = FakeClient()  # type: ignore[assignment]
        try:
            result = api_server.answer_from_document_rag(
                "Summarize the uploaded document",
                [{"role": "user", "content": "Uploaded file:\n- handbook.txt"}],
                [
                    {
                        "title": "Handbook",
                        "content": "Orientation is mandatory. Registration is required before classes begin.",
                        "source": "handbook.txt",
                    }
                ],
                "no-supabase-session",
                attached_files=["handbook.txt"],
            )
        finally:
            api_server.AI_CLIENT = original_client

        self.assertTrue(result["found_match"])
        self.assertIn("Orientation", result["answer"])

    def test_uploaded_context_filters_out_non_attached_faq_chunks(self) -> None:
        original_client = api_server.AI_CLIENT

        class FakeClient:
            is_configured = True

            def answer_from_context(self, **kwargs):
                matches = kwargs.get("matches") or []
                return matches[0].chunk.text if matches else "LLM answer"

            def answer_freeform(self, **kwargs):
                return "LLM freeform answer"

        api_server.AI_CLIENT = FakeClient()  # type: ignore[assignment]
        try:
            result = api_server.answer_from_uploaded_context(
                "Summarize the uploaded document",
                [],
                [
                    {
                        "title": "Project 2 Mode",
                        "content": "The assistant processes uploaded university documents through project mode logic.",
                        "source": "faq-project-2",
                    },
                    {
                        "title": "Handbook",
                        "content": "Orientation is mandatory. Registration is required before classes begin.",
                        "source": "ERAZiDStirldg75Ot2E880BS2sFHy6mz3edJYxms.pdf",
                    },
                ],
                attached_files=["ERAZiDStirldg75Ot2E880BS2sFHy6mz3edJYxms.pdf"],
            )
        finally:
            api_server.AI_CLIENT = original_client

        self.assertTrue(result["found_match"])
        self.assertIn("Orientation", result["answer"])
        self.assertNotIn("project mode", result["answer"].lower())

    def test_uploaded_context_does_not_fall_back_to_unattached_faq_chunks(self) -> None:
        result = api_server.answer_from_uploaded_context(
            "Summarize the uploaded document",
            [],
            [
                {
                    "title": "Canvas Feature Notes",
                    "content": "Canvas creates editable website or uploaded-document evidence summaries.",
                    "source": "faq-project-3",
                }
            ],
            attached_files=["handbook.pdf"],
        )

        self.assertFalse(result["found_match"])
        self.assertNotIn("routing keywords", result["answer"].lower())
        self.assertIn("readable text", result["answer"].lower())

    def test_website_answer_returns_model_unavailable_when_gemini_quota_fails(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class QuotaFailingClient:
            is_configured = True
            last_error = "quota exceeded, check billing"

            def answer_freeform(self, **kwargs):
                raise RuntimeError(self.last_error)

            def answer_from_context(self, **kwargs):
                raise RuntimeError(self.last_error)

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "admission-0",
                                "url": "https://daffodilvarsity.edu.bd/admission",
                                "title": "Admission Information",
                                "text": (
                                    "Daffodil International University provides admission information "
                                    "for undergraduate and graduate applicants. Students can explore "
                                    "program options and start the application journey from the admission portal."
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=QuotaFailingClient(),
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "Tell me about DIU admission information",
                [],
                "quota-fallback-session",
                [],
                "assistant",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertFalse(result["found_match"])
        self.assertFalse(result["used_model"])
        self.assertIn("rate-limited", result["answer"].lower())
        self.assertFalse(result["sources"])

    def test_university_answer_uses_general_assistant_without_special_routing(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class EchoGeminiClient:
            is_configured = True
            last_error = ""

            def answer_freeform(self, **kwargs):
                return "Gemini generated scholarship answer"

            def answer_from_context(self, **kwargs):
                return "Gemini generated scholarship answer"

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 3, "chunks_count": 3},
                        "chunks": [
                            {
                                "id": "admission-0",
                                "url": "https://daffodilvarsity.edu.bd/admission",
                                "title": "Admission Information",
                                "text": "DIU admission guidance covers application requirements and eligibility.",
                            },
                            {
                                "id": "programs-0",
                                "url": "https://daffodilvarsity.edu.bd/programs",
                                "title": "Programs",
                                "text": "DIU programs include undergraduate and postgraduate academic options.",
                            },
                            {
                                "id": "scholarship-0",
                                "url": "https://daffodilvarsity.edu.bd/scholarship",
                                "title": "Scholarships",
                                "text": "DIU offers scholarships, waivers, and financial aid opportunities.",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=EchoGeminiClient(),
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "What scholarship or waiver options are available?",
                [],
                "general-canvas-session",
                [],
                "assistant",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertIn("scholarship", result["answer"].lower())
        self.assertEqual(result["artifacts"], [])

    def test_plain_assistant_mode_does_not_create_canvas_artifacts(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class EchoGeminiClient:
            is_configured = True
            last_error = ""

            def answer_freeform(self, **kwargs):
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                return "Gemini generated answer"

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "scholarship-0",
                                "url": "https://daffodilvarsity.edu.bd/scholarship",
                                "title": "Scholarships",
                                "text": "DIU offers scholarships and tuition waivers for students.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=EchoGeminiClient(),
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "What scholarship opportunities are available at DIU?",
                [],
                "assistant-no-canvas-session",
                [],
                "assistant",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertEqual(result["answer"], "Gemini generated answer")
        self.assertEqual(result["artifacts"], [])

    def test_agent_mode_does_not_create_canvas_until_explicitly_requested(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class EchoGeminiClient:
            is_configured = True
            last_error = ""

            def answer_freeform(self, **kwargs):
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                return "Gemini generated answer"

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "admission-0",
                                "url": "https://daffodilvarsity.edu.bd/admission",
                                "title": "Admission",
                                "text": "Admission information for DIU applicants.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=EchoGeminiClient(),
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            normal_result = api_server.answer_from_university_knowledge(
                "Answer in DIU Admission Mode.\n\nUser question: What are the admission requirements?",
                [],
                "agent-no-canvas-session",
                [],
                "admission",
            )
            canvas_result = api_server.answer_from_university_knowledge(
                "Answer in DIU Admission Mode.\n\nUser question: Generate an interactive visual version of our last discussion now. [canvas force unlock]",
                [],
                "agent-with-canvas-session",
                [],
                "admission",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertEqual(normal_result["artifacts"], [])
        self.assertTrue(canvas_result["artifacts"])

    def test_explicit_canvas_request_uses_model_to_build_website(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class WebsiteGeminiClient:
            is_configured = True
            last_error = ""
            received_question = ""

            def answer_freeform(self, **kwargs):
                self.received_question = kwargs["user_question"]
                return self._html()

            def answer_from_context(self, **kwargs):
                self.received_question = kwargs["user_question"]
                return self._html()

            def _html(self):
                return """```html
<!doctype html>
<html lang="en">
<head><title>Admission Website</title></head>
<body><main><section><h1>Admission Website</h1><p>Documents and payment steps.</p></section></main></body>
</html>
```"""

        try:
            gemini_client = WebsiteGeminiClient()
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "admission-0",
                                "url": "https://daffodilvarsity.edu.bd/admission",
                                "title": "Admission",
                                "text": "Admission information for DIU applicants.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=gemini_client,
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "Answer in DIU Admission Mode.\n\nUser question: Create a complete standalone website from the following content. [canvas force unlock]\n\nAdmission checklist with documents and payment steps.",
                [],
                "canvas-short-circuit-session",
                [],
                "admission",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertTrue(result["artifacts"])
        self.assertEqual(result["answer"], "Here is your workspace. Open the canvas to explore it.")
        self.assertTrue(result["used_model"])
        self.assertIn("complete standalone website", gemini_client.received_question)

        html_path = resolve_artifact_path(
            api_server.CANVAS_ARTIFACTS_DIR,
            "canvas-short-circuit-session",
            result["artifacts"][0]["id"],
        )
        self.assertIsNotNone(html_path)
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("Admission Website", html)
        self.assertNotIn("DIU Workspace", html)

    def test_ranking_question_stays_general(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class EchoGeminiClient:
            is_configured = True
            last_error = ""

            def answer_freeform(self, **kwargs):
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                return "Gemini generated answer"

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "rankings-latest",
                                "url": "https://research.daffodilvarsity.edu.bd/rankings",
                                "title": "DoR - Division of Research | DIU",
                                "text": (
                                    "QS World University Rankings: Asia 2026 DIU ranks #221 in Asia; "
                                    "#43 in South Asia and #2 Private University in Bangladesh."
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=EchoGeminiClient(),
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "diu ranking?",
                [],
                "ranking-canvas-session",
                [],
                "assistant",
                allow_local_grounding=True,
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertTrue(result["found_match"])
        self.assertEqual(result["answer"], "Gemini generated answer")
        self.assertEqual(result["sources"][0]["url"], "https://research.daffodilvarsity.edu.bd/rankings")

    def test_general_faq_question_stays_general(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class EchoGeminiClient:
            is_configured = True
            last_error = ""

            def answer_freeform(self, **kwargs):
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                return "Gemini generated answer"

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "home-0",
                                "url": "https://daffodilvarsity.edu.bd",
                                "title": "Daffodil International University",
                                "text": "Daffodil International University (DIU) is a private university in Bangladesh with a permanent campus and broad academic community.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=EchoGeminiClient(),
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "What is DIU?",
                [],
                "general-faq-canvas-session",
                [],
                "assistant",
                allow_local_grounding=True,
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertTrue(result["found_match"])
        self.assertEqual(result["answer"], "Gemini generated answer")
        self.assertEqual(result["sources"][0]["url"], "https://daffodilvarsity.edu.bd")

    def test_live_only_university_answer_skips_local_grounding_sources(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class TrackingGeminiClient:
            is_configured = True
            last_error = ""
            last_call = None

            def answer_freeform(self, **kwargs):
                self.last_call = ("freeform", kwargs)
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                self.last_call = ("context", kwargs)
                return "Gemini generated answer"

        gemini = TrackingGeminiClient()

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "home-0",
                                "url": "https://daffodilvarsity.edu.bd",
                                "title": "Daffodil International University",
                                "text": "Daffodil International University (DIU) is a private university in Bangladesh.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=gemini,
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "What is DIU?",
                [],
                "general-live-only-session",
                [],
                "assistant",
                allow_local_grounding=False,
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertTrue(result["found_match"])
        self.assertEqual(result["answer"], "Gemini generated answer")
        self.assertEqual(result["sources"], [])
        self.assertEqual(gemini.last_call[0], "freeform")

    def test_university_answer_defaults_to_no_local_grounding(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class TrackingGeminiClient:
            is_configured = True
            last_error = ""
            last_call = None

            def answer_freeform(self, **kwargs):
                self.last_call = ("freeform", kwargs)
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                self.last_call = ("context", kwargs)
                return "Gemini generated answer"

        gemini = TrackingGeminiClient()

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "programs-0",
                                "url": "https://daffodilvarsity.edu.bd/programs",
                                "title": "Programs",
                                "text": "DIU offers many academic programs.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=gemini,
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "What programs does DIU offer?",
                [],
                "default-live-only-session",
                [],
                "assistant",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertTrue(result["found_match"])
        self.assertEqual(result["answer"], "Gemini generated answer")
        self.assertNotIn("What I did", result["answer"])
        self.assertEqual(result["sources"], [])
        self.assertEqual(gemini.last_call[0], "freeform")

    def test_course_question_uses_general_canvas_flow_without_extra_tools(self) -> None:
        original_bot = api_server.WEBSITE_BOT
        original_pipeline_factory = api_server.get_document_pipeline
        temp_dir = tempfile.TemporaryDirectory()

        class TrackingGeminiClient:
            is_configured = True
            last_error = ""
            last_call = None

            def answer_freeform(self, **kwargs):
                self.last_call = ("freeform", kwargs)
                return "Gemini generated answer"

            def answer_from_context(self, **kwargs):
                self.last_call = ("context", kwargs)
                return "Gemini generated answer"

        gemini = TrackingGeminiClient()

        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "metadata": {"pages_count": 1, "chunks_count": 1},
                        "chunks": [
                            {
                                "id": "programs-0",
                                "url": "https://daffodilvarsity.edu.bd/programs",
                                "title": "Programs",
                                "text": "DIU offers CSE and other academic programs.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            api_server.WEBSITE_BOT = DIUCampusChatbot(
                index_path,
                gemini_client=gemini,
                auto_sync=False,
            )
            api_server.get_document_pipeline = lambda session_id: None  # type: ignore[assignment]

            result = api_server.answer_from_university_knowledge(
                "Which courses should I explore for CSE?",
                [],
                "course-canvas-session",
                [],
                "assistant",
            )
        finally:
            api_server.WEBSITE_BOT = original_bot
            api_server.get_document_pipeline = original_pipeline_factory  # type: ignore[assignment]
            temp_dir.cleanup()

        self.assertEqual(result["answer"], "Gemini generated answer")
        self.assertNotIn("What I did", result["answer"])
        self.assertNotIn("Program matcher detected", result["answer"])
        self.assertIsNotNone(gemini.last_call)


if __name__ == "__main__":
    unittest.main()
