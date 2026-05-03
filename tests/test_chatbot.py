from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.knowledge import DIUCampusChatbot


class FailingGeminiClient:
    is_configured = True
    last_error = "API_KEY_INVALID: API key not valid"

    def answer_freeform(self, **kwargs):
        raise RuntimeError(self.last_error)

    def answer_from_context(self, **kwargs):
        raise RuntimeError(self.last_error)


class DailyQuotaGeminiClient(FailingGeminiClient):
    last_error = (
        "Quota exceeded for metric: generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash-lite "
        "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    )


class EchoGeminiClient:
    is_configured = True
    enable_google_search = True
    last_error = ""
    last_call = None

    def answer_freeform(self, **kwargs):
        self.last_call = ("freeform", kwargs)
        return "Gemini generated answer"

    def answer_from_context(self, **kwargs):
        self.last_call = ("context", kwargs)
        return "Gemini generated answer"


class DIUCampusChatbotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.index_path = Path(cls.temp_dir.name) / "site_index.json"
        payload = {
            "metadata": {"pages_count": 3, "chunks_count": 4},
            "chunks": [
                {
                    "id": "admission-0",
                    "url": "https://daffodilvarsity.edu.bd/admission",
                    "title": "Admission Information",
                    "text": "Daffodil International University provides admission information for undergraduate and graduate students. Applicants can explore program options and start the application journey from the admission portal.",
                },
                {
                    "id": "scholarship-0",
                    "url": "https://daffodilvarsity.edu.bd/scholarship",
                    "title": "Scholarships That Unlock Potential",
                    "text": "DIU highlights scholarship opportunities and tuition waivers for eligible students. The university mentions many scholarship categories for learners with strong merit and financial need.",
                },
                {
                    "id": "research-0",
                    "url": "https://daffodilvarsity.edu.bd/research",
                    "title": "Research and Innovation at DIU",
                    "text": "The university presents research centers, patents, peer reviewed papers, and research partnerships. DIU describes research as a major part of its innovation culture.",
                },
                {
                    "id": "contact-0",
                    "url": "https://daffodilvarsity.edu.bd/contact",
                    "title": "Contact DIU",
                    "text": "Students can reach DIU through the official contact section and admission support pages for information requests and campus communication.",
                },
            ],
        }
        cls.index_path.write_text(json.dumps(payload), encoding="utf-8")
        cls.bot = DIUCampusChatbot(
            cls.index_path,
            gemini_client=EchoGeminiClient(),
            auto_sync=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_index_loads(self) -> None:
        self.assertTrue(self.bot.has_index)
        self.assertEqual(self.bot.index_metadata["pages_count"], 3)

    def test_greeting_gets_helpful_reply(self) -> None:
        response = self.bot.answer("hello")
        self.assertTrue(response.found_match)
        self.assertEqual(response.category, "chat")
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")

    def test_greeting_uses_gemini_when_configured(self) -> None:
        gemini = EchoGeminiClient()
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=gemini,
            auto_sync=False,
        )

        response = bot.answer(
            "hello",
            chat_history=[
                {"role": "user", "content": "What scholarships are available?"},
                {"role": "assistant", "content": "DIU offers scholarships and waivers."},
            ],
        )

        self.assertEqual(response.category, "chat")
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertEqual(gemini.last_call[0], "freeform")
        self.assertEqual(len(gemini.last_call[1]["chat_history"]), 2)
        self.assertFalse(response.source_urls)

    def test_spanish_greeting_does_not_use_sources(self) -> None:
        response = self.bot.answer("hola")
        self.assertTrue(response.found_match)
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")

    def test_casual_chat_answers_without_retrieval(self) -> None:
        response = self.bot.answer("thank you")
        self.assertTrue(response.found_match)
        self.assertEqual(response.category, "chat")
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertFalse(response.source_urls)

    def test_clarification_turn_uses_gemini_when_configured(self) -> None:
        gemini = EchoGeminiClient()
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=gemini,
            auto_sync=False,
        )

        response = bot.answer(
            "huh?",
            chat_history=[
                {"role": "user", "content": "If I fail HSC, can I get admission at DIU?"},
                {"role": "assistant", "content": "Admission eligibility depends on official DIU requirements."},
            ],
        )

        self.assertTrue(response.found_match)
        self.assertEqual(response.category, "chat")
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertEqual(gemini.last_call[0], "freeform")
        self.assertEqual(len(gemini.last_call[1]["chat_history"]), 2)
        self.assertFalse(response.source_urls)

    def test_admission_question_retrieves_indexed_content(self) -> None:
        response = self.bot.answer("Tell me about DIU admission information", allow_local_grounding=True)
        self.assertTrue(response.found_match)
        self.assertEqual(response.category, "website")
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertIn("https://daffodilvarsity.edu.bd/admission", response.source_urls)

    def test_scholarship_question_returns_source(self) -> None:
        response = self.bot.answer("What scholarship opportunities does DIU mention?", allow_local_grounding=True)
        self.assertTrue(response.found_match)
        self.assertTrue(response.source_urls)
        self.assertIn("scholarship", response.source_urls[0])

    def test_unknown_question_falls_back_safely(self) -> None:
        response = self.bot.answer("What is the weather in Tokyo today?")
        self.assertTrue(response.found_match)
        self.assertEqual(response.category, "chat")
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")

    def test_configured_gemini_handles_diu_question(self) -> None:
        gemini = EchoGeminiClient()
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=gemini,
            auto_sync=False,
        )

        response = bot.answer("Tell me about DIU admission information", allow_local_grounding=True)

        self.assertTrue(response.found_match)
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertEqual(gemini.last_call[0], "context")
        self.assertIn("https://daffodilvarsity.edu.bd/admission", response.source_urls)
        self.assertFalse(gemini.last_call[1]["enable_search"])

    def test_freshness_sensitive_diu_question_keeps_live_search_enabled(self) -> None:
        gemini = EchoGeminiClient()
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=gemini,
            auto_sync=False,
        )

        response = bot.answer("What are the latest DIU admission deadlines?", allow_local_grounding=True)

        self.assertTrue(response.used_gemini)
        self.assertEqual(gemini.last_call[0], "context")
        self.assertTrue(gemini.last_call[1]["enable_search"])

    def test_truncated_answer_detector_flags_dangling_sentence(self) -> None:
        text = (
            "DIU offers several scholarship and waiver categories for undergraduate students. "
            "These include merit support, female student waivers, and special quota benefits. "
            "One of the common benefits is"
        )

        self.assertTrue(self.bot._looks_truncated_answer(text))

    def test_truncated_answer_detector_ignores_complete_sentence(self) -> None:
        text = (
            "DIU offers several scholarship and waiver categories for undergraduate students. "
            "These include merit support, female student waivers, and special quota benefits. "
            "One of the common benefits is a 20% tuition fee waiver."
        )

        self.assertFalse(self.bot._looks_truncated_answer(text))

    def test_configured_gemini_declines_non_diu_questions_even_when_not_in_off_topic_keyword_list(self) -> None:
        gemini = EchoGeminiClient()
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=gemini,
            auto_sync=False,
        )

        response = bot.answer("What is artificial intelligence?")

        self.assertTrue(response.found_match)
        self.assertEqual(response.category, "chat")
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertEqual(gemini.last_call[0], "freeform")
        self.assertFalse(response.source_urls)

    def test_configured_gemini_receives_session_history_for_followups(self) -> None:
        gemini = EchoGeminiClient()
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=gemini,
            auto_sync=False,
        )

        response = bot.answer(
            "What about scholarships?",
            chat_history=[
                {"role": "user", "content": "Tell me about DIU admission information"},
                {"role": "assistant", "content": "DIU provides admission information for undergraduate and graduate students."},
            ],
        )

        self.assertTrue(response.found_match)
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertIsNotNone(gemini.last_call)
        self.assertEqual(gemini.last_call[1]["chat_history"][0]["content"], "Tell me about DIU admission information")

    def test_live_only_mode_skips_local_grounding_and_uses_freeform(self) -> None:
        gemini = EchoGeminiClient()
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=gemini,
            auto_sync=False,
        )

        response = bot.answer(
            "Tell me about DIU admission information",
            allow_local_grounding=False,
        )

        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")
        self.assertEqual(gemini.last_call[0], "freeform")
        self.assertFalse(response.source_urls)

    def test_bangla_query_gets_bangla_wrapper(self) -> None:
        response = self.bot.answer("DIU তে scholarship সম্পর্কে বলুন")
        self.assertTrue(response.found_match)
        self.assertEqual(response.language, "bn")
        self.assertTrue(response.used_gemini)
        self.assertEqual(response.answer, "Gemini generated answer")

    def test_short_followup_uses_recent_context(self) -> None:
        response = self.bot.answer(
            "what about waivers?",
            chat_history=[
                {"role": "user", "content": "Tell me about DIU scholarship opportunities"},
                {"role": "assistant", "content": "DIU highlights scholarship opportunities."},
            ],
            allow_local_grounding=True,
        )

        self.assertTrue(response.found_match)
        self.assertIn("scholarship", response.source_urls[0])

    def test_short_followup_can_use_assistant_context(self) -> None:
        query = self.bot._contextualize_query(
            "is it good for career?",
            [
                {"role": "user", "content": "Tell me about MCT"},
                {
                    "role": "assistant",
                    "content": "MCT includes animation, game development, graphic design, and interactive technology.",
                },
            ],
        )

        self.assertIn("Session topic: Tell me about MCT", query)
        self.assertIn("Relevant recent context:", query)
        self.assertIn("game development", query)

    def test_contextualized_query_expands_vague_followup(self) -> None:
        query = self.bot._contextualize_query(
            "what about that?",
            [
                {"role": "user", "content": "Tell me about game development"},
                {"role": "assistant", "content": "Game development involves design, programming, art, and testing."},
                {"role": "user", "content": "what about that?"},
            ],
        )

        self.assertIn("Session topic: Tell me about game development", query)
        self.assertIn("Relevant recent context:", query)
        self.assertIn("programming, art, and testing", query)

    def test_more_detailed_followup_expands_with_latest_substantive_context(self) -> None:
        query = self.bot._contextualize_query(
            "more detailed?",
            [
                {"role": "user", "content": "Tell me about DIU admission information"},
                {"role": "assistant", "content": "DIU admission depends on the program and current official requirements."},
                {"role": "user", "content": "Tell me about DIU scholarship opportunities"},
                {"role": "assistant", "content": "DIU scholarship opportunities include waivers for eligible students."},
            ],
        )

        self.assertIn("Session topic: Tell me about DIU scholarship opportunities", query)
        self.assertNotIn("Session topic: Tell me about DIU admission information", query)
        self.assertIn("Relevant recent context:", query)

    def test_explicit_compare_question_is_not_rewritten_as_followup(self) -> None:
        query = self.bot._contextualize_query(
            "compare CSE and SWE",
            [
                {"role": "user", "content": "Tell me about DIU admission information"},
                {"role": "assistant", "content": "DIU admission depends on the program and current official requirements."},
            ],
        )

        self.assertEqual(query, "compare CSE and SWE")

    def test_scholarship_retrieval_prefers_actual_scholarship_page_over_research_pages(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 2},
                "chunks": [
                    {
                        "id": "research-0",
                        "url": "https://research.daffodilvarsity.edu.bd/director-message",
                        "title": "DoR - Division of Research | DIU",
                        "text": "At Daffodil International University research is a major driver of innovation and academic excellence.",
                    },
                    {
                        "id": "scholarship-0",
                        "url": "https://daffodilvarsity.edu.bd/scholarship",
                        "title": "Scholarship Opportunities at DIU",
                        "text": "Explore various scholarship opportunities at DIU including waivers and financial support categories.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            matches = bot.retrieve("What scholarship opportunities are available at DIU?", top_k=4)

            self.assertTrue(matches)
            self.assertEqual(matches[0].chunk.url, "https://daffodilvarsity.edu.bd/scholarship")
        finally:
            temp_dir.cleanup()

    def test_fsit_department_question_prefers_fsit_faculty_evidence_over_program_faq(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "programs-0",
                        "url": "https://daffodilvarsity.edu.bd/programs",
                        "title": "Programs at DIU",
                        "text": "Browse undergraduate and graduate programs across six faculties with departments and admission information.",
                    },
                    {
                        "id": "fsit-0",
                        "url": "https://webbackend.daffodilvarsity.edu.bd/faculty/fsit",
                        "title": "Faculty of Science & Information Technology",
                        "text": "The department of Computing and Information System (CIS) and the Department of Information Technology and Management (ITM) are listed under the Faculty of Science and Information Technology.",
                    },
                    {
                        "id": "testimonial-0",
                        "url": "https://daffodilvarsity.edu.bd/testimonial",
                        "title": "Student Testimonial",
                        "text": "A student says the faculty helped with career growth and programs.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("Which departments are under the FSIT faculty?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertEqual(response.source_urls[0], "https://webbackend.daffodilvarsity.edu.bd/faculty/fsit")
            self.assertNotIn("testimonial", " ".join(response.source_urls).lower())
        finally:
            temp_dir.cleanup()

    def test_cse_curriculum_question_prefers_specific_department_sources(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "programs-0",
                        "url": "https://daffodilvarsity.edu.bd/programs",
                        "title": "Programs at DIU",
                        "text": "DIU programs include CSE, departments, courses, and undergraduate pathways.",
                    },
                    {
                        "id": "cse-0",
                        "url": "https://daffodilvarsity.edu.bd/department/cse",
                        "title": "Department of CSE",
                        "text": "Each CSE card links to full program details including curriculum, admissions requirements, and faculty contacts.",
                    },
                    {
                        "id": "cse-program-0",
                        "url": "https://daffodilvarsity.edu.bd/department/cse/program/bse-in-cse",
                        "title": "BSc in CSE",
                        "text": "The CSE program page contains program details, courses, curriculum, and credit information for students.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("Tell me about the CSE course curriculum", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertIn("/department/cse", response.source_urls[0])
            self.assertNotEqual(response.source_urls[0], "https://daffodilvarsity.edu.bd/programs")
        finally:
            temp_dir.cleanup()

    def test_demandable_department_question_uses_demand_sources_not_generic_or_testimonials(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 4, "chunks_count": 4},
                "chunks": [
                    {
                        "id": "programs-0",
                        "url": "https://daffodilvarsity.edu.bd/programs",
                        "title": "Programs at DIU",
                        "text": "DIU offers programs by faculty and department for students choosing courses.",
                    },
                    {
                        "id": "testimonial-0",
                        "url": "https://daffodilvarsity.edu.bd/testimonial",
                        "title": "Career Testimonial",
                        "text": "A student testimonial says software engineering helped with career scope and job demand.",
                    },
                    {
                        "id": "fsit-0",
                        "url": "https://webbackend.daffodilvarsity.edu.bd/faculty/fsit",
                        "title": "Faculty of Science & Information Technology",
                        "text": "Software Engineering is committed to satisfy the growing demands of software professionals and produce skilled manpower for the global IT Market.",
                    },
                    {
                        "id": "swe-lab-0",
                        "url": "https://daffodilvarsity.edu.bd/lab-facilities/swe",
                        "title": "Software Engineering Lab Facilities",
                        "text": "The Software Engineering labs support Data Science, Cyber Security, Robotics, algorithms, web programming, and mobile application development.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("diu best department? i mean most demandable", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertEqual(response.source_urls[0], "https://webbackend.daffodilvarsity.edu.bd/faculty/fsit")
            self.assertNotIn("testimonial", " ".join(response.source_urls).lower())
        finally:
            temp_dir.cleanup()

    def test_broad_scholarship_question_keeps_detailed_scholarship_pages_with_faq(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            faq_path = Path(temp_dir.name) / "diu_faqs.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "scholarship-0",
                        "url": "https://daffodilvarsity.edu.bd/scholarship",
                        "title": "Scholarship Opportunities at DIU",
                        "text": "Explore various scholarship opportunities at DIU including waivers and financial support.",
                    },
                    {
                        "id": "scholarships-0",
                        "url": "https://daffodilvarsity.edu.bd/scholarships",
                        "title": "Waiver and Scholarship",
                        "text": "DIU says 80% of students receive a waiver or scholarship and mentions result-based, merit-based, need-based, and diversity support.",
                    },
                    {
                        "id": "calculator-0",
                        "url": "https://daffodilvarsity.edu.bd/tuition-fee-calculator",
                        "title": "Tuition Fee Calculator",
                        "text": "Students can estimate tuition fees with applicable waivers and scholarships.",
                    },
                ],
            }
            faq_payload = [
                {
                    "id": "scholarship-overview",
                    "category": "scholarship",
                    "question_variants": {"en": ["scholarship?"]},
                    "answer": {"en": "DIU offers scholarships and waivers."},
                    "keywords": ["scholarship", "waiver"],
                    "source_url": "https://daffodilvarsity.edu.bd/scholarship",
                }
            ]
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            faq_path.write_text(json.dumps(faq_payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("What scholarship opportunities are available at DIU?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertEqual(response.source_urls[0], "https://daffodilvarsity.edu.bd/scholarships")
            self.assertIn("https://daffodilvarsity.edu.bd/scholarship", response.source_urls)
            self.assertIn("https://daffodilvarsity.edu.bd/tuition-fee-calculator", response.source_urls)
        finally:
            temp_dir.cleanup()

    def test_program_cost_query_keeps_program_context_before_fee_context(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "research-physics-0",
                        "url": "https://research.daffodilvarsity.edu.bd/astrophysics",
                        "title": "DIU Astrophysics Center",
                        "text": "The DIU Astrophysics Center supports astronomy and physics research activities.",
                    },
                    {
                        "id": "programs-0",
                        "url": "https://daffodilvarsity.edu.bd/programs",
                        "title": "Programs at DIU",
                        "text": "DIU lists undergraduate and graduate programs by faculty, department, and degree level.",
                    },
                    {
                        "id": "fees-0",
                        "url": "https://daffodilvarsity.edu.bd/tuition-fee-calculator",
                        "title": "Tuition Fee Calculator",
                        "text": "Students can discover tuition fees with applicable waivers and admission payment breakdowns.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            raw_matches = bot.retrieve("How much would it cost me to graduate from DIU in Physics?", top_k=6)
            selected = bot._select_local_matches("How much would it cost me to graduate from DIU in Physics?", raw_matches)

            self.assertEqual(bot._primary_intent("How much would it cost me to graduate from DIU in Physics?"), "programs")
            self.assertTrue(selected)
            self.assertEqual(selected[0].chunk.url, "https://daffodilvarsity.edu.bd/programs")
            self.assertIn(
                "https://daffodilvarsity.edu.bd/tuition-fee-calculator",
                [match.chunk.url for match in selected],
            )
            self.assertNotIn(
                "https://research.daffodilvarsity.edu.bd/astrophysics",
                [match.chunk.url for match in selected[:2]],
            )
        finally:
            temp_dir.cleanup()

    def test_program_cost_query_returns_model_unavailable_when_gemini_fails(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "programs-0",
                        "url": "https://daffodilvarsity.edu.bd/programs",
                        "title": "Programs at DIU",
                        "text": "DIU offers undergraduate and graduate pathways across multiple faculties and programs.",
                    },
                    {
                        "id": "fees-0",
                        "url": "https://daffodilvarsity.edu.bd/tuition-fee-calculator",
                        "title": "Tuition Fee Calculator",
                        "text": "Students can estimate tuition fees with applicable waivers and admission payment breakdowns.",
                    },
                    {
                        "id": "home-0",
                        "url": "https://daffodilvarsity.edu.bd",
                        "title": "Daffodil International University",
                        "text": "The homepage highlights programs, faculties, scholarships, and student services.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(
                index_path,
                gemini_client=FailingGeminiClient(),
                auto_sync=False,
            )

            response = bot.answer("How much would it cost me to graduate from DIU in Physics?")

            self.assertFalse(response.found_match)
            self.assertEqual(response.category, "system")
            self.assertIn("api key", response.answer.lower())
            self.assertNotIn("visitor statistics", response.answer.lower())
        finally:
            temp_dir.cleanup()

    def test_mct_teacher_panel_uses_faculty_evidence_not_fake_login_steps(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 2},
                "chunks": [
                    {
                        "id": "mct-0",
                        "url": "https://webbackend.daffodilvarsity.edu.bd/department/mct",
                        "title": "Multimedia & Creative Technology",
                        "text": (
                            "Official MoU Signing with Future Studios Bangladesh. "
                            "Mr. Md. Salah Uddin – Assistant Professor & Head, MCT,DIU "
                            "Mr. Arif Ahmed – Professor of Practice, MCT,DIU "
                            "Mr. Kazi Jahid Hasan – Assistant Professor, MCT,DIU"
                        ),
                    },
                    {
                        "id": "teachers-0",
                        "url": "https://daffodilvarsity.edu.bd/teachers",
                        "title": "Daffodil International University",
                        "text": "Deans & Heads Associate Deans & Heads Visiting Professors Faculty Members",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("mct department teacher panel", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertTrue(response.used_gemini)
            self.assertEqual(response.answer, "Gemini generated answer")
            self.assertTrue(response.source_urls)
            self.assertNotIn("Password", response.answer)
            self.assertNotIn("Two-Factor", response.answer)
        finally:
            temp_dir.cleanup()

    def test_generic_admission_question_does_not_ground_on_mct_department(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 2},
                "chunks": [
                    {
                        "id": "admission-0",
                        "url": "https://daffodilvarsity.edu.bd/admission",
                        "title": "Admission Requirements",
                        "text": "DIU admission requirements explain how undergraduate applicants can apply and submit documents.",
                    },
                    {
                        "id": "mct-0",
                        "url": "https://daffodilvarsity.edu.bd/department/mct/admission-eligibility",
                        "title": "MCT Admission Eligibility",
                        "text": "MCT admission eligibility includes SSC, HSC, GPA, program, course, department, and requirement details.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("What are the admission requirements at DIU?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertTrue(response.used_gemini)
            self.assertNotIn("/department/mct", " ".join(response.source_urls).lower())
        finally:
            temp_dir.cleanup()

    def test_short_qs_ranking_question_uses_latest_ranking_context(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "rankings-old",
                        "url": "https://research.daffodilvarsity.edu.bd/rankings",
                        "title": "DoR - Division of Research | DIU",
                        "text": "DIU Ranked within Top 400 Asian Universities by QS World University Rankings Asia 2022.",
                    },
                    {
                        "id": "rankings-latest",
                        "url": "https://research.daffodilvarsity.edu.bd/rankings",
                        "title": "DoR - Division of Research | DIU",
                        "text": "QS World University Rankings: Asia 2026 DIU ranks #221 in Asia; #43 in South Asia and #2 Private University in Bangladesh. QS World University Rankings 2026: DIU positions 1001-1200 globally.",
                    },
                    {
                        "id": "news-rankings",
                        "url": "https://news.daffodilvarsity.edu.bd",
                        "title": "Home-Daffodil International University Media Corner",
                        "text": "Earlier, DIU secured a position in the QS World Sustainability Rankings 2024.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("qs ranking?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertTrue(response.used_gemini)
            self.assertEqual(response.answer, "Gemini generated answer")
            self.assertEqual(response.source_urls[0], "https://research.daffodilvarsity.edu.bd/rankings")
            self.assertIn("Asia 2026", bot.gemini_client.last_call[1]["matches"][0].chunk.text)
        finally:
            temp_dir.cleanup()

    def test_qs_ranking_question_prefers_qs_publisher_profile(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "research-ranking",
                        "url": "https://research.daffodilvarsity.edu.bd/rankings",
                        "title": "DoR - Division of Research | DIU",
                        "text": "QS World University Rankings 2026: DIU positions 1001-1200 globally.",
                    },
                    {
                        "id": "news-the-ranking",
                        "url": "https://news.daffodilvarsity.edu.bd/news/daffodil-international-university-ranks-first-in-bangladesh-in-the-world-university-rankings-2025",
                        "title": "Daffodil International University Ranks First in Bangladesh in THE World University Rankings 2025",
                        "text": "Daffodil International University ranked first in Bangladesh in THE World University Rankings 2025.",
                    },
                    {
                        "id": "qs-profile",
                        "url": "https://www.topuniversities.com/universities/daffodil-international-university",
                        "title": "Daffodil International University : Rankings, Fees & Courses Details | TopUniversities",
                        "text": "Daffodil International University is ranked #1001-1200 in QS World University Rankings 2026 and #=221 in Asian University Rankings.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("What is DIU QS ranking?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertEqual(response.source_urls[0], "https://www.topuniversities.com/universities/daffodil-international-university")
            self.assertEqual(response.source_titles[0], "QS TopUniversities Profile")
        finally:
            temp_dir.cleanup()

    def test_the_ranking_question_prefers_times_higher_education_profile(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "wiki-ranking",
                        "url": "https://en.wikipedia.org/wiki/Daffodil_International_University",
                        "title": "Daffodil International University - Wikipedia",
                        "text": "DIU ranked jointly 1st in Bangladesh in THE World University Rankings 2025.",
                    },
                    {
                        "id": "news-the-ranking",
                        "url": "https://news.daffodilvarsity.edu.bd/news/daffodil-international-university-ranks-first-in-bangladesh-in-the-world-university-rankings-2025",
                        "title": "Daffodil International University Ranks First in Bangladesh in THE World University Rankings 2025",
                        "text": "Daffodil International University ranked first in Bangladesh in THE World University Rankings 2025.",
                    },
                    {
                        "id": "the-profile",
                        "url": "https://www.timeshighereducation.com/world-university-rankings/daffodil-international-university-diu",
                        "title": "Daffodil International University (DIU) | World University Rankings | THE",
                        "text": "World University Rankings 2026 801-1000th. Impact Rankings 2025 101-200th. Quality Education 2025 19th.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("What is DIU THE ranking?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertEqual(response.source_urls[0], "https://www.timeshighereducation.com/world-university-rankings/daffodil-international-university-diu")
            self.assertEqual(response.source_titles[0], "Times Higher Education Profile")
        finally:
            temp_dir.cleanup()

    def test_university_overview_prefers_homepage_summary_over_news_noise(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 2},
                "chunks": [
                    {
                        "id": "news-0",
                        "url": "https://news.daffodilvarsity.edu.bd",
                        "title": "Home-Daffodil International University Media Corner",
                        "text": "He added, I am particularly encouraged by research and innovation at Daffodil International University.",
                    },
                    {
                        "id": "home-0",
                        "url": "https://daffodilvarsity.edu.bd",
                        "title": "Daffodil International University",
                        "text": (
                            "Becoming a globally recognized center of excellence through innovative, learner-centric, "
                            "technology-driven education, and impactful research. 38 programs, 6 faculties, "
                            "Undergraduate and Graduate pathways."
                        ),
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("Tell me about Daffodil International University in short", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertTrue(response.used_gemini)
            self.assertEqual(response.answer, "Gemini generated answer")
            self.assertIn("https://daffodilvarsity.edu.bd", response.source_urls)
        finally:
            temp_dir.cleanup()

    def test_university_overview_prefers_official_homepage_over_wikipedia(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 2, "chunks_count": 2},
                "chunks": [
                    {
                        "id": "wiki-overview",
                        "url": "https://en.wikipedia.org/wiki/Daffodil_International_University",
                        "title": "Daffodil International University - Wikipedia",
                        "text": "Daffodil International University is a private research university in Bangladesh.",
                    },
                    {
                        "id": "official-overview",
                        "url": "https://daffodilvarsity.edu.bd/",
                        "title": "Daffodil International University Official Homepage",
                        "text": "Vision: becoming a globally recognized center of excellence through learner-centric education. 38 programs, 6 faculties, undergraduate and graduate pathways.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("Tell me about DIU official overview", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertEqual(response.source_urls[0], "https://daffodilvarsity.edu.bd/")
        finally:
            temp_dir.cleanup()

    def test_curated_faq_file_is_ignored_for_scholarship_question(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            faq_path = Path(temp_dir.name) / "diu_faqs.json"
            payload = {
                "metadata": {"pages_count": 1, "chunks_count": 1},
                "chunks": [
                    {
                        "id": "scholarship-0",
                        "url": "https://daffodilvarsity.edu.bd/scholarship",
                        "title": "Scholarship Page",
                        "text": "Explore various scholarship opportunities at DIU.",
                    },
                ],
            }
            faq_payload = [
                {
                    "id": "scholarship-opportunities-overview",
                    "category": "scholarship",
                    "language": "bilingual",
                    "question_variants": {
                        "en": ["What scholarship opportunities are available at DIU?"],
                        "bn": [],
                    },
                    "answer": {
                        "en": "Scholarship overview.\n\n| Criteria | Waiver |\n| --- | --- |\n| Golden GPA-5 | 50% |",
                        "bn": "",
                    },
                    "keywords": ["scholarship", "waiver", "golden gpa 5"],
                    "source_url": "https://daffodilvarsity.edu.bd/scholarship",
                    "last_verified": "2026-04-21",
                }
            ]
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            faq_path.write_text(json.dumps(faq_payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("What scholarship opportunities are available at DIU?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertTrue(response.used_gemini)
            self.assertEqual(response.answer, "Gemini generated answer")
            self.assertIsNone(response.matched_faq_id)
            self.assertIn("https://daffodilvarsity.edu.bd/scholarship", response.source_urls)
        finally:
            temp_dir.cleanup()

    def test_curated_faq_file_is_ignored_for_hsc_fail_question(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            faq_path = Path(temp_dir.name) / "diu_faqs.json"
            payload = {
                "metadata": {"pages_count": 1, "chunks_count": 1},
                "chunks": [
                    {
                        "id": "admission-0",
                        "url": "https://daffodilvarsity.edu.bd/admission",
                        "title": "Admission Information",
                        "text": "Applicants should check the admission process, eligibility criteria, and HSC/SSC requirements on the official DIU admission page.",
                    },
                ],
            }
            faq_payload = [
                {
                    "id": "hsc-fail-admission-guidance",
                    "category": "admission",
                    "language": "bilingual",
                    "question_variants": {
                        "en": ["If I fail in HSC, can I admit myself at DIU?"],
                        "bn": [],
                    },
                    "answer": {
                        "en": "If you fail in HSC, you should not assume that you can get admitted to a DIU honours program.\n\n1. Programs and Eligibility",
                        "bn": "",
                    },
                    "keywords": ["fail in hsc", "gpa 2.50", "admission"],
                    "source_url": "https://daffodilvarsity.edu.bd/admission-contact",
                    "last_verified": "2026-04-21",
                }
            ]
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            faq_path.write_text(json.dumps(faq_payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("If I fail in HSC, can I admit myself at DIU?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertTrue(response.used_gemini)
            self.assertEqual(response.answer, "Gemini generated answer")
            self.assertIsNone(response.matched_faq_id)
            self.assertIn("https://daffodilvarsity.edu.bd/admission", response.source_urls)
        finally:
            temp_dir.cleanup()

    def test_interpreted_guidance_response_handles_ambiguous_curriculum_question_cautiously(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            faq_path = Path(temp_dir.name) / "diu_faqs.json"
            payload = {
                "metadata": {"pages_count": 1, "chunks_count": 1},
                "chunks": [
                    {
                        "id": "cse-page-0",
                        "url": "https://admission.daffodilvarsity.edu.bd/",
                        "title": "Engineering Programs",
                        "text": "B.Sc. in Computer Science and Engineering is listed as a 4-year program with 148 credits.",
                    },
                ],
            }
            faq_payload = [
                {
                    "id": "cse-program-duration-credit",
                    "category": "programs",
                    "language": "bilingual",
                    "question_variants": {
                        "en": ["What is the duration and credit load of CSE at DIU?"],
                        "bn": [],
                    },
                    "answer": {
                        "en": "The DIU admission page lists B.Sc. in Computer Science and Engineering as a 4-year program with 148 credits.",
                        "bn": "",
                    },
                    "keywords": ["cse", "148 credits", "4 year"],
                    "source_url": "https://admission.daffodilvarsity.edu.bd/",
                    "last_verified": "2026-04-21",
                }
            ]
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            faq_path.write_text(json.dumps(faq_payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            response = bot.answer("will i be learning drawing in cse ?", allow_local_grounding=True)

            self.assertTrue(response.found_match)
            self.assertTrue(response.used_gemini)
            self.assertEqual(response.category, "website")
            self.assertEqual(response.answer, "Gemini generated answer")
            self.assertEqual(response.source_titles, ["Admission Page"])
        finally:
            temp_dir.cleanup()

    def test_configured_gemini_failure_returns_model_unavailable_message_for_admission(self) -> None:
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=FailingGeminiClient(),
            auto_sync=False,
        )

        response = bot.answer("If I fail HSC, can I admit myself at DIU?")

        self.assertFalse(response.found_match)
        self.assertEqual(response.category, "system")
        self.assertIn("api key", response.answer.lower())

    def test_model_unavailable_returns_provider_error_for_scholarship(self) -> None:
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=FailingGeminiClient(),
            auto_sync=False,
        )

        response = bot.answer("What scholarship opportunities does DIU mention?")

        self.assertFalse(response.found_match)
        self.assertEqual(response.category, "system")
        self.assertIn("api key", response.answer.lower())

    def test_daily_free_tier_quota_message_is_not_short_retry(self) -> None:
        bot = DIUCampusChatbot(
            self.index_path,
            gemini_client=DailyQuotaGeminiClient(),
            auto_sync=False,
        )

        response = bot.answer("What scholarship opportunities does DIU mention?")

        self.assertFalse(response.found_match)
        self.assertEqual(response.category, "system")
        self.assertIn("free daily usage limit", response.answer.lower())
        self.assertIn("current project", response.answer.lower())

    def test_hsc_failure_query_prefers_admission_pages_over_noisy_pages(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 4, "chunks_count": 4},
                "chunks": [
                    {
                        "id": "admission-0",
                        "url": "https://daffodilvarsity.edu.bd/admission-contact",
                        "title": "Admission Information",
                        "text": "Official DIU admission requirements and eligibility should be confirmed from the admission office. Admission support is available through the official contact channels.",
                    },
                    {
                        "id": "eligibility-0",
                        "url": "https://daffodilvarsity.edu.bd/department/mct/admission-eligibility",
                        "title": "MCT Admission Eligibility",
                        "text": "This page links to admission requirements, eligibility guidance, tuition details, and faculty contacts for applicants.",
                    },
                    {
                        "id": "alumni-0",
                        "url": "https://alumni.daffodilvarsity.edu.bd",
                        "title": "Home",
                        "text": "I really feel proud to introduce myself as an alumnus of DIU.",
                    },
                    {
                        "id": "research-0",
                        "url": "https://research.daffodilvarsity.edu.bd/video-gallery",
                        "title": "DoR - Division of Research | DIU",
                        "text": "Shaping the future: strategic research directions at DIU.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(index_path, gemini_client=EchoGeminiClient(), auto_sync=False)

            matches = bot.retrieve("If I fail HSC, can I admit myself at DIU?", top_k=4)
            selected = bot._select_local_matches("If I fail HSC, can I admit myself at DIU?", matches)

            self.assertTrue(selected)
            self.assertIn("daffodilvarsity.edu.bd", selected[0].chunk.url)
            self.assertIn("admission", selected[0].chunk.url)
            self.assertNotIn("alumni.daffodilvarsity.edu.bd", selected[0].chunk.url)
            self.assertFalse(any("/department/" in match.chunk.url for match in selected))
        finally:
            temp_dir.cleanup()

    def test_hsc_failure_query_returns_model_unavailable_when_model_fails(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            index_path = Path(temp_dir.name) / "site_index.json"
            payload = {
                "metadata": {"pages_count": 3, "chunks_count": 3},
                "chunks": [
                    {
                        "id": "admission-0",
                        "url": "https://daffodilvarsity.edu.bd/admission-contact",
                        "title": "Admission Information",
                        "text": "Official DIU admission requirements and eligibility should be confirmed from the admission office.",
                    },
                    {
                        "id": "eligibility-0",
                        "url": "https://daffodilvarsity.edu.bd/department/mct/admission-eligibility",
                        "title": "MCT Admission Eligibility",
                        "text": "Admission requirements and eligibility details are available from the official DIU admission pages.",
                    },
                    {
                        "id": "alumni-0",
                        "url": "https://alumni.daffodilvarsity.edu.bd",
                        "title": "Home",
                        "text": "I really feel proud to introduce myself as an alumnus of DIU.",
                    },
                ],
            }
            index_path.write_text(json.dumps(payload), encoding="utf-8")
            bot = DIUCampusChatbot(
                index_path,
                gemini_client=FailingGeminiClient(),
                auto_sync=False,
            )

            response = bot.answer("If I fail HSC, can I admit myself at DIU?")

            self.assertFalse(response.found_match)
            self.assertEqual(response.category, "system")
            self.assertIn("api key", response.answer.lower())
            self.assertFalse(response.source_urls)
        finally:
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
