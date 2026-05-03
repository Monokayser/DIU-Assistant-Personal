from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.apps.documents.rag.pipeline import RAGPipeline, _contextualize_query, parse_uploaded_file, supported_upload_extensions
from tests.fakes import FakeSupabaseClient


class SuccessfulGemini:
    is_configured = True

    def answer_from_context(self, **kwargs: object) -> str:
        self.last_context_kwargs = kwargs
        matches = kwargs.get("matches") or []
        if matches:
            return str(matches[0].chunk.text)
        return "LLM answer from uploaded documents."

    def answer_freeform(self, **kwargs: object) -> str:
        self.last_freeform_kwargs = kwargs
        return "LLM freeform answer."


class RAGPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = RAGPipeline(
            api_key="",
            gemini_client=SuccessfulGemini(),
            session_id=self.id(),
            supabase_client=FakeSupabaseClient(),
        )

    def test_ingest_and_answer_from_uploaded_documents(self) -> None:
        handbook = (
            "Student Handbook\n\n"
            "Admission requirements include academic transcripts, a completed application form, "
            "and a passport-size photograph. Orientation is mandatory for new students."
        ).encode("utf-8")
        scholarship = (
            "Scholarship Policy\n\n"
            "Merit scholarships and tuition waivers are available for students with strong academic results. "
            "Renewal depends on maintaining the required CGPA."
        ).encode("utf-8")

        self.pipeline.ingest_file(handbook, "student_handbook.txt")
        self.pipeline.ingest_file(scholarship, "scholarship_policy.txt")

        response = self.pipeline.answer_query("What are the admission requirements?")

        self.assertTrue(response.found_match)
        self.assertEqual(response.category, "documents")
        self.assertIn("admission requirements", response.answer.lower())
        self.assertIn("student_handbook.txt", response.source_urls)

    def test_document_answers_receive_session_history(self) -> None:
        handbook = (
            "Student Handbook\n\n"
            "The software engineering track covers requirements analysis, testing, and maintenance."
        ).encode("utf-8")
        self.pipeline.ingest_file(handbook, "student_handbook.txt")

        response = self.pipeline.answer_query(
            "chart?",
            chat_history=[
                {"role": "user", "content": "Compare CSE vs software engineering"},
                {"role": "assistant", "content": "CSE is broader, while software engineering focuses more on software lifecycle work."},
            ],
            preferred_sources=["student_handbook.txt"],
            prefer_attached=True,
        )

        self.assertTrue(response.found_match)
        self.assertEqual(
            self.pipeline.gemini_client.last_context_kwargs["chat_history"][0]["content"],
            "Compare CSE vs software engineering",
        )
        self.assertIn(
            "Session topic: Compare CSE vs software engineering",
            self.pipeline.gemini_client.last_context_kwargs["user_question"],
        )

    def test_document_answers_limit_context_matches_sent_to_model(self) -> None:
        for index in range(12):
            content = (
                f"Course Handbook {index}\n\n"
                "Admission requirements include transcripts, application forms, and student policies."
            ).encode("utf-8")
            self.pipeline.ingest_file(content, f"handbook_{index}.txt")

        response = self.pipeline.answer_query("Summarize the admission requirements from the uploaded documents.")

        self.assertTrue(response.found_match)
        self.assertLessEqual(len(self.pipeline.gemini_client.last_context_kwargs["matches"]), 8)

    def test_contextualize_query_uses_latest_substantive_user_topic(self) -> None:
        query = _contextualize_query(
            "more detailed?",
            [
                {"role": "user", "content": "Tell me about DIU admission information"},
                {"role": "assistant", "content": "DIU admission depends on the program."},
                {"role": "user", "content": "Tell me about DIU scholarship opportunities"},
                {"role": "assistant", "content": "DIU offers scholarships and waivers."},
            ],
        )

        self.assertIn("Session topic: Tell me about DIU scholarship opportunities", query)
        self.assertNotIn("Session topic: Tell me about DIU admission information", query)

    def test_contextualize_query_does_not_rewrite_explicit_compare_question(self) -> None:
        query = _contextualize_query(
            "compare CSE and SWE",
            [
                {"role": "user", "content": "Tell me about DIU admission information"},
                {"role": "assistant", "content": "DIU admission depends on the program."},
            ],
        )

        self.assertEqual(query, "compare CSE and SWE")

    def test_clear_resets_uploaded_documents(self) -> None:
        self.pipeline.ingest_file(b"Course catalog with semester plan.", "catalog.txt")
        self.assertTrue(self.pipeline.has_documents)

        self.pipeline.clear()

        self.assertFalse(self.pipeline.has_documents)
        self.assertEqual(self.pipeline.document_count, 0)
        self.assertEqual(self.pipeline.chunk_count, 0)

    def test_reingesting_same_source_replaces_stale_chunks(self) -> None:
        self.pipeline.ingest_text(
            "Old unreadable upload data should not survive a corrected re-upload.",
            "student_handbook.pdf",
        )
        self.pipeline.ingest_text(
            "Fresh handbook text says orientation is mandatory before classes begin.",
            "student_handbook.pdf",
        )

        combined_text = " ".join(chunk.text for chunk in self.pipeline.vector_store.chunks)
        self.assertIn("Fresh handbook", combined_text)
        self.assertNotIn("Old unreadable", combined_text)

    def test_daily_upload_formats_are_parsed_as_text(self) -> None:
        json_text = parse_uploaded_file(b'{"policy":{"title":"Scholarship","cgpa":3.75}}', "policy.json")
        html_text = parse_uploaded_file(b"<h1>Admission Notice</h1><p>Bring transcripts.</p>", "notice.html")
        code_text = parse_uploaded_file(b"def admission_check():\n    return True\n", "rules.py")

        self.assertIn("Scholarship", json_text)
        self.assertIn("Admission Notice", html_text)
        self.assertIn("admission_check", code_text)

    def test_supported_upload_extensions_include_common_assistant_files(self) -> None:
        extensions = supported_upload_extensions()

        for extension in [".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".png", ".py"]:
            self.assertIn(extension, extensions)

    def test_summary_request_can_use_attached_file_without_keyword_overlap(self) -> None:
        text = (
            "Student Handbook\n\n"
            "Orientation is mandatory for all newly admitted students and takes place before classes begin. "
            "Students must complete registration and attend the onboarding sessions.\n\n"
            "The handbook also explains the academic calendar, support services, and student conduct expectations."
        )

        self.pipeline.ingest_text(text, "student_handbook.txt")

        response = self.pipeline.answer_query(
            "Summarize the uploaded document",
            preferred_sources=["student_handbook.txt"],
            prefer_attached=True,
        )

        self.assertTrue(response.found_match)
        self.assertIn("student_handbook.txt", response.source_urls)
        self.assertIn("orientation", response.answer.lower())

    def test_attached_document_scope_does_not_freeform_without_documents(self) -> None:
        class FakeGemini:
            is_configured = True

            def answer_freeform(self, **kwargs: object) -> str:
                return "This freeform answer should not be used."

        pipeline = RAGPipeline(
            api_key="",
            gemini_client=FakeGemini(),
            session_id=f"{self.id()}-empty",
            supabase_client=FakeSupabaseClient(),
        )

        response = pipeline.answer_query(
            "Summarize the uploaded document",
            preferred_sources=["student_handbook.pdf"],
            prefer_attached=True,
        )

        self.assertFalse(response.found_match)
        self.assertIn("readable text", response.answer.lower())
        self.assertNotIn("freeform", response.answer.lower())

    def test_clean_model_text_removes_provider_identity_leak(self) -> None:
        cleaned = self.pipeline._clean_model_text("As an AI language model, I am Gemini. Here is the summary.")

        self.assertNotIn("Gemini", cleaned)
        self.assertNotIn("AI language model", cleaned)
        self.assertIn("DIU Assistant", cleaned)

    def test_local_memory_store_is_used_when_supabase_is_not_configured(self) -> None:
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_ANON_KEY": ""}, clear=False):
            pipeline = RAGPipeline(
                api_key="",
                gemini_client=SuccessfulGemini(),
                session_id=f"{self.id()}-local-memory",
            )

            stored = pipeline.ingest_text(
                "Local fallback upload should stay searchable for the current app session.",
                "local-memory-note.txt",
            )
            response = pipeline.answer_query(
                "Summarize the uploaded document",
                preferred_sources=["local-memory-note.txt"],
                prefer_attached=True,
            )

        self.assertEqual(pipeline.vector_backend, "local-memory")
        self.assertEqual(stored, 1)
        self.assertTrue(pipeline.has_documents)
        self.assertIn("local-memory-note.txt", response.source_urls)
        self.assertTrue(response.found_match)

    def test_document_answer_requires_live_model_when_matches_exist(self) -> None:
        class FailingGemini:
            is_configured = True

            def answer_from_context(self, **kwargs: object) -> str:
                raise RuntimeError("quota exceeded, check billing")

            def answer_freeform(self, **kwargs: object) -> str:
                raise RuntimeError("quota exceeded, check billing")

        pipeline = RAGPipeline(
            api_key="",
            gemini_client=FailingGemini(),
            session_id=f"{self.id()}-model-required",
            supabase_client=FakeSupabaseClient(),
        )

        pipeline.ingest_text(
            "Student Handbook. Admission requirements include academic transcripts and orientation.",
            "student_handbook.txt",
        )
        response = pipeline.answer_query("What are the admission requirements?")

        self.assertFalse(response.found_match)
        self.assertEqual(response.category, "system")
        self.assertIn("live llm", response.answer.lower())

    def test_document_answer_requires_live_model_without_extractive_fallback(self) -> None:
        pipeline = RAGPipeline(
            api_key="",
            session_id=f"{self.id()}-model-required-no-fallback",
            supabase_client=FakeSupabaseClient(),
        )

        pipeline.ingest_text(
            "Course Catalog. The CSE program includes algorithms, databases, operating systems, and AI electives.",
            "course_catalog.txt",
        )
        response = pipeline.answer_query(
            "Summarize the uploaded document",
            preferred_sources=["course_catalog.txt"],
            prefer_attached=True,
        )

        self.assertFalse(response.found_match)
        self.assertEqual(response.category, "system")
        self.assertFalse(response.used_gemini)
        self.assertIn("live llm", response.answer.lower())
        self.assertFalse(response.source_urls)


if __name__ == "__main__":
    unittest.main()
