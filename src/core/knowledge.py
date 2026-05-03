from __future__ import annotations

import json
import os
import re
import sys
import traceback
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from typing import Any

from src.apps.documents.rag.ingestion import build_site_index
from src.api.errors import extract_retry_after_seconds, format_backend_error, is_daily_free_tier_quota
from src.core.observability import log_event, normalize_question, truncate_text


STOPWORDS_EN = {
    "a", "about", "an", "and", "are", "can", "for", "how", "i", "in", "is",
    "me", "my", "of", "please", "tell", "the", "to", "what", "where", "who", "with",
}
STOPWORDS_BN = {
    "এবং", "একটি", "একটা", "এর", "কত", "কি", "কী", "কিভাবে", "কীভাবে",
    "জানতে", "চাই", "আমি", "আমার", "কোথায়", "কে", "বলুন",
}
INTENT_TERMS = {
    "admission": {"admission", "admit", "admitted", "apply", "application", "eligibility", "eligible", "requirement", "hsc", "ssc", "gpa", "ভর্তি", "যোগ্যতা"},
    "scholarship": {
        "scholarship", "scholarships", "waiver", "waivers", "tuition",
        "tuition coverage", "fee", "fees", "financial", "stipend",
        "স্কলারশিপ", "ওয়েভার",
    },
    "programs": {"program", "degree", "faculty", "department", "course", "graduate", "graduation", "major", "subject", "study", "studying", "physics", "প্রোগ্রাম", "বিভাগ"},
    "research": {"research", "innovation", "paper", "patent", "lab", "rank", "ranked", "ranking", "rankings", "qs", "গবেষণা", "ইনোভেশন"},
    "contact": {"contact", "phone", "email", "office", "help desk", "যোগাযোগ", "ফোন", "ইমেইল"},
    "campus": {"campus", "student life", "club", "facility", "hall", "ক্যাম্পাস", "সুবিধা"},
    "fees": {"tuition", "fee", "cost", "payment", "amount", "expense", "expenses", "ফি", "খরচ", "টাকা"},
}
INTENT_PRIORITY = {
    "admission": {"admission", "apply", "information", "admission-contact"},
    "scholarship": {"scholarship", "waiver", "tuition-fee-calculator"},
    "programs": {"program", "faculty", "faculties", "students"},
    "research": {"research", "innovation", "paper", "patent", "rank", "ranking", "rankings", "qs"},
    "contact": {"contact", "location", "admission-contact", "support"},
    "campus": {"campus", "students", "parents", "alumni", "life"},
    "fees": {"tuition", "fee", "calculator", "waiver"},
}
INTENT_HOST_PREFERENCE = {
    "research": {"research.daffodilvarsity.edu.bd"},
    "contact": {"daffodilvarsity.edu.bd", "it.daffodilvarsity.edu.bd"},
    "programs": {"daffodilvarsity.edu.bd", "admission.daffodilvarsity.edu.bd"},
    "admission": {"daffodilvarsity.edu.bd", "admission.daffodilvarsity.edu.bd"},
    "scholarship": {"daffodilvarsity.edu.bd", "admission.daffodilvarsity.edu.bd"},
    "fees": {"daffodilvarsity.edu.bd", "admission.daffodilvarsity.edu.bd"},
}
DEPARTMENT_ALIASES = {
    "mct": {"multimedia", "creative", "technology", "department", "mct"},
    "cse": {"computer", "science", "engineering", "cse"},
    "swe": {"software", "engineering", "swe"},
    "cis": {"computing", "information", "system", "cis"},
    "itm": {"information", "technology", "management", "itm"},
    "eee": {"electrical", "electronic", "engineering", "eee"},
    "bba": {"business", "administration", "bba"},
}
QUERY_PHRASE_ALIASES = {
    "average student": {"general", "student"},
    "admit himself": {"admission", "eligibility", "apply"},
    "admit herself": {"admission", "eligibility", "apply"},
    "want to admit": {"admission", "eligibility", "apply"},
    "can i admit": {"admission", "eligibility", "apply"},
    "can i get admission": {"admission", "eligibility", "apply"},
    "fail in hsc": {"admission", "eligibility", "hsc"},
    "failed hsc": {"admission", "eligibility", "hsc"},
    "hsc fail": {"admission", "eligibility", "hsc"},
    "qs ranking": {"diu", "qs", "ranking", "rankings"},
    "graduate from diu in": {"program", "degree", "tuition", "fee"},
    "cost to graduate": {"program", "degree", "tuition", "fee"},
    "diu in physics": {"program", "degree", "physics"},
    "physics": {"program", "degree", "physics"},
}
OFF_TOPIC_ALLOWLIST = {
    "diu", "daffodil", "varsity", "admission", "scholarship", "faculty", "department",
    "campus", "academic", "fee", "program", "study", "education", "course", "degree",
    "apply", "student", "teacher", "professor", "exam", "result", "varsity", "campus-life"
}


@dataclass
class SiteChunk:
    id: str
    url: str
    title: str
    text: str
    normalized_text: str
    tokens: set[str]
    title_tokens: set[str]
    url_tokens: set[str]
    source_type: str = "site"
    category: str | None = None


@dataclass
class ChunkMatch:
    chunk: SiteChunk
    score: float


@dataclass
class ChatResponse:
    question: str
    answer: str
    category: str
    source_url: str | None
    language: str
    confidence: float
    found_match: bool
    used_gemini: bool
    matched_faq_id: str | None
    source_urls: list[str]
    source_titles: list[str]


class DIUCampusChatbot:
    def __init__(
        self,
        site_index_path: str | Path,
        *,
        gemini_client: Any | None = None,
        min_confidence: float = 0.18,
        auto_sync: bool = False,
        base_url: str = "https://daffodilvarsity.edu.bd/",
    ) -> None:
        self.site_index_path = Path(site_index_path)
        self.gemini_client = gemini_client
        self.min_confidence = min_confidence
        self.base_url = base_url
        self.index_metadata: dict[str, Any] = {}
        self.chunks: list[SiteChunk] = []
        self.retrieval_top_k = int(os.getenv("DIU_RAG_RETRIEVAL_TOP_K", "80"))
        self.context_match_limit = int(os.getenv("DIU_RAG_CONTEXT_MATCHES", "8"))
        self.fallback_match_limit = int(os.getenv("DIU_RAG_FALLBACK_MATCHES", "8"))
        if auto_sync and not self.site_index_path.exists():
            self.sync_site_data()
        self._load_index_if_available()

    @property
    def has_index(self) -> bool:
        return bool(self.chunks)

    def sync_site_data(self) -> dict[str, Any]:
        metadata = build_site_index(self.base_url, self.site_index_path)
        self._load_index_if_available()
        return metadata

    # ------------------------------------------------------------------
    # Main answer entry point — everything goes through Gemini
    # ------------------------------------------------------------------

    def answer(
        self,
        question: str,
        *,
        chat_history: list[dict[str, Any]] | None = None,
        allow_local_grounding: bool = False,
        mode: str = "assistant",
    ) -> ChatResponse:
        clean_question = (question or "").strip()
        language = self.detect_language(clean_question)
        contextualized_question = self._extract_user_question_text(
            self._contextualize_query(clean_question, chat_history)
        )

        if not clean_question:
            return self._empty_response(clean_question, language)

        # Retrieve DIU context only to ground Gemini. The bot response itself
        # must always come from Gemini, never from local/prewritten fallbacks.
        matches: list[ChunkMatch] = []
        source_urls: list[str] = []
        source_titles: list[str] = []

        if allow_local_grounding and self.has_index:
            retrieval_query = contextualized_question
            raw_matches = self.retrieve(retrieval_query, top_k=self.retrieval_top_k)


            matches = self._select_local_matches(retrieval_query, raw_matches)
            if not matches:
                matches = [
                    match for match in raw_matches
                    if match.score >= 0.0 and not self._is_noisy_chunk(match.chunk)
                ][: self.fallback_match_limit]
            matches = matches[: self.context_match_limit]

            self._log_grounding_event(
                retrieval_query,
                mode=mode,
                raw_matches=raw_matches,
                selected_matches=matches,
            )
            source_urls = self._unique_urls(matches) if matches else []
            source_titles = self._unique_titles(matches) if matches else []

        if not self._gemini_is_configured():
            return self._not_configured_response(clean_question, language)

        # Always let Gemini answer
        try:
            enable_search = self._should_use_live_search(contextualized_question, matches)
            if allow_local_grounding and matches and matches[0].score >= 0.0:
                answer = self.gemini_client.answer_from_context(
                    user_question=contextualized_question,
                    matches=matches,
                    language=language,
                    chat_history=chat_history,
                    mode=mode,
                    enable_search=enable_search,
                )
            else:
                answer = self.gemini_client.answer_freeform(
                    user_question=contextualized_question,
                    language=language,
                    chat_history=chat_history,
                    mode=mode,
                    enable_search=enable_search,
                )
        except Exception as exc:
            print(f"[DIU Assistant] Gemini call failed: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return self._model_unavailable_response(clean_question, language)
        # Merge any grounding sources from Gemini with RAG sources
        urls, titles = self._merge_gemini_sources(source_urls, source_titles)

        return ChatResponse(
            question=clean_question,
            answer=answer,
            category="website" if matches else "chat",
            source_url=urls[0] if urls else None,
            language=language,
            confidence=1.0,
            found_match=True,
            used_gemini=True,
            matched_faq_id=None,
            source_urls=urls,
            source_titles=titles,
        )

    def stream_answer(
        self,
        question: str,
        *,
        chat_history: list[dict[str, Any]] | None = None,
        allow_local_grounding: bool = False,
        mode: str = "assistant",
    ):
        clean_question = (question or "").strip()
        language = self.detect_language(clean_question)
        contextualized_question = self._extract_user_question_text(
            self._contextualize_query(clean_question, chat_history)
        )

        if not clean_question:
            yield {"chunk": ""}
            return

        matches: list[ChunkMatch] = []
        source_urls: list[str] = []
        source_titles: list[str] = []

        if allow_local_grounding and self.has_index:
            retrieval_query = contextualized_question
            raw_matches = self.retrieve(retrieval_query, top_k=self.retrieval_top_k)


            matches = self._select_local_matches(retrieval_query, raw_matches)
            if not matches:
                matches = [
                    match for match in raw_matches
                    if match.score >= 0.0 and not self._is_noisy_chunk(match.chunk)
                ][: self.fallback_match_limit]
            matches = matches[: self.context_match_limit]


            self._log_grounding_event(
                retrieval_query,
                mode=mode,
                raw_matches=raw_matches,
                selected_matches=matches,
            )
            source_urls = self._unique_urls(matches) if matches else []
            source_titles = self._unique_titles(matches) if matches else []

        if not self._gemini_is_configured():
            yield {"error": "Gemini API key is not configured."}
            return

        # Check for canvas signal early
        is_canvas = "[canvas force unlock]" in clean_question.lower() or "[canvas force unlock]" in contextualized_question.lower()
        if is_canvas and "[canvas force unlock]" not in contextualized_question.lower():
            contextualized_question = f"{contextualized_question} [canvas force unlock]"

        try:
            full_answer = ""
            enable_search = self._should_use_live_search(contextualized_question, matches)
            if allow_local_grounding and matches and matches[0].score >= 0.0:
                stream = self.gemini_client.stream_answer_from_context(
                    user_question=contextualized_question,
                    matches=matches,
                    language=language,
                    chat_history=chat_history,
                    mode=mode,
                    enable_search=enable_search,
                )
            else:
                stream = self.gemini_client.stream_answer_freeform(
                    user_question=contextualized_question,
                    language=language,
                    chat_history=chat_history,
                    mode=mode,
                    enable_search=enable_search,
                )
            
            # Send initial signals
            if is_canvas:
                yield {"status": "generating_artifact"}
            if self._is_off_topic(contextualized_question, matches):
                yield {"status": "off_topic"}

            for chunk in stream:
                full_answer += chunk
                yield {"chunk": chunk}
            
            # Merge sources at the end
            urls, titles = self._merge_gemini_sources(source_urls, source_titles)
            sources = [
                {"title": title, "url": url if str(url).startswith("http") else None, "source": url if not str(url).startswith("http") else None}
                for title, url in zip(titles, urls)
            ]
            if self._looks_truncated_answer(full_answer):
                raise RuntimeError("The streamed answer ended before the final sentence completed.")
            yield {
                "done": True,
                "answer": full_answer,
                "sources": sources[:3],
                "model_name": self.gemini_client.last_successful_model,
                "used_model": True,
            }
        except Exception as exc:
            print(f"[DIU Assistant] Gemini stream failed: {exc}", file=sys.stderr)
            yield {"error": format_backend_error(exc)}

    def _should_use_live_search(self, question: str, matches: list[ChunkMatch]) -> bool:
        if not self.gemini_client or not getattr(self.gemini_client, "enable_google_search", False):
            return False

        normalized = self._normalize_text(question)
        if self._is_freshness_sensitive_question(normalized):
            return True

        if matches:
            top_score = matches[0].score
            if top_score >= 0.12: # Instant local-first: skip search even for modest matches
                return False
            return top_score < 0.05 # Only search if we are extremely unsure

        intent = self._primary_intent(question)
        return bool(intent)

    def _is_off_topic(self, question: str, matches: list[ChunkMatch]) -> bool:
        normalized = self._normalize_text(question)
        
        # 1. Direct Keyword Check (Fastest)
        if any(term in normalized for term in OFF_TOPIC_ALLOWLIST):
            return False
        
        # 2. Contextual Grounding Check
        # If we have strong local matches, it's inherently on-topic for the university assistant
        if matches and matches[0].score > 0.12:
            return False
            
        # 3. Brief Social Interaction Check
        # Allow short phrases like "hello", "hi", "how are you" to keep the bot friendly
        if len(normalized.split()) < 4:
            return False

        return True

    def _looks_truncated_answer(self, answer: str) -> bool:
        text = re.sub(r"\s+", " ", str(answer or "")).strip()
        if len(text) < 50:
            return False
        if re.search(r'([.!?]|</\w+>|```)\s*["\')\]]*\s*$', text):
            return False
        if text.endswith((",", ":", ";", "-", "/", "(")):
            return True
        last_word_match = re.search(r"([A-Za-z]+)\s*$", text)
        if not last_word_match:
            return False
        return last_word_match.group(1).lower() in {
            "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
            "in", "into", "is", "of", "on", "or", "the", "to", "under", "with",
            "can", "will", "should", "could", "would", "must", "may", "might",
            "has", "have", "had", "does", "do", "did", "was", "were", "but", "so"
        }

    def _select_local_matches(self, question: str, matches: list[ChunkMatch]) -> list[ChunkMatch]:
        if not matches:
            return []

        intent = self._primary_intent(question)
        requested_department = self._requested_department_alias(question)
        if self._is_ranking_question(question):
            ranking_matches = [
                match for match in matches
                if match.score >= 0.06 and self._chunk_mentions_rankings(match.chunk)
            ]
            if ranking_matches:
                ranking_matches.sort(key=lambda match: self._ranking_evidence_score(match, question), reverse=True)
                return self._dedupe_matches(ranking_matches)[:4]
        if self._is_university_overview_question(question):
            overview_matches = [
                match for match in matches
                if match.score >= 0.06 and self._is_official_overview_chunk(match.chunk)
            ]
            if overview_matches:
                overview_matches.sort(key=self._overview_evidence_score, reverse=True)
                remaining = [match for match in matches if match not in overview_matches and not self._is_noisy_chunk(match.chunk)]
                return self._dedupe_matches([*overview_matches, *remaining])[:4]

        specific_matches = self._select_specific_academic_matches(question, matches, intent, requested_department)
        if specific_matches:
            return specific_matches

        if intent == "programs" and self._is_program_cost_question(question):
            usable = [
                match for match in matches
                if match.score >= 0.06 and not self._is_noisy_chunk(match.chunk)
            ]
        else:
            minimum_score = 0.08 if intent else self.min_confidence
            usable = [
                match for match in matches
                if match.score >= minimum_score and self._match_supports_intent(match.chunk, intent)
            ]
            if any(not self._is_noisy_chunk(match.chunk) for match in usable):
                usable = [match for match in usable if not self._is_noisy_chunk(match.chunk)]
            if intent == "admission" and not requested_department and any("/department/" not in match.chunk.url for match in usable):
                usable = [match for match in usable if "/department/" not in match.chunk.url]
            if intent == "admission" and not self._is_eligibility_concern(question) and any(not self._is_eligibility_chunk(match.chunk) for match in usable):
                usable = [match for match in usable if not self._is_eligibility_chunk(match.chunk)]
            if intent == "campus" and any(not self._is_noisy_chunk(match.chunk) for match in usable):
                usable = [match for match in usable if not self._is_noisy_chunk(match.chunk)]
            if not usable and intent:
                usable = [
                    match for match in matches
                    if match.score >= self.min_confidence and not self._is_noisy_chunk(match.chunk)
                ]
        if intent in {"programs", "admission", "fees"}:
            if requested_department:
                department_filtered = [
                    match for match in usable
                    if not self._is_department_chunk(match.chunk)
                    or self._department_alias_for_chunk(match.chunk) == requested_department
                ]
                if department_filtered:
                    usable = department_filtered
            elif any(not self._is_department_chunk(match.chunk) for match in usable):
                usable = [match for match in usable if not self._is_department_chunk(match.chunk)]
        if not usable:
            return []

        if intent == "programs" and self._is_program_cost_question(question):
            program_matches = [
                match for match in usable
                if any(term in f"{match.chunk.title} {match.chunk.url}".lower() for term in ("program", "faculty", "department", "admission"))
            ]
            fee_matches = [
                match for match in usable
                if any(term in f"{match.chunk.title} {match.chunk.url} {match.chunk.text}".lower() for term in ("fee", "tuition", "waiver", "payment"))
            ]
            ordered = self._dedupe_matches([*program_matches, *fee_matches, *usable])
            return ordered[:4]

        return self._dedupe_matches(usable)[:8]

    def _select_specific_academic_matches(
        self,
        question: str,
        matches: list[ChunkMatch],
        intent: str | None,
        requested_department: str | None,
    ) -> list[ChunkMatch]:
        if intent == "scholarship" and self._is_broad_scholarship_question(question):
            scholarship_matches = [
                match for match in matches
                if match.score >= 0.06 and self._is_scholarship_detail_source(match.chunk)
            ]
            if scholarship_matches:
                scholarship_matches.sort(key=self._scholarship_evidence_score, reverse=True)
                return self._dedupe_matches(scholarship_matches)[:6]

        if intent != "programs":
            return []

        if self._is_fsit_department_question(question):
            fsit_matches = [
                match for match in matches
                if match.score >= 0.06 and self._is_fsit_department_source(match.chunk)
            ]
            if fsit_matches:
                fsit_matches.sort(key=self._fsit_evidence_score, reverse=True)
                return self._dedupe_matches(fsit_matches)[:5]

        if self._is_demandable_department_question(question):
            demand_matches = [
                match for match in matches
                if match.score >= 0.06 and self._is_demand_program_source(match.chunk)
            ]
            if demand_matches:
                demand_matches.sort(key=lambda match: self._academic_specificity_score(match, question, requested_department), reverse=True)
                return self._dedupe_matches(demand_matches)[:6]

        if requested_department and self._is_curriculum_or_program_detail_question(question):
            department_matches = [
                match for match in matches
                if match.score >= 0.06 and self._is_requested_department_source(match.chunk, requested_department)
            ]
            if department_matches:
                department_matches.sort(key=lambda match: self._academic_specificity_score(match, question, requested_department), reverse=True)
                return self._dedupe_matches(department_matches)[:5]

        return []

    def _primary_intent(self, question: str) -> str | None:
        normalized = self._normalize_text(question)
        if self._is_program_cost_question(normalized):
            return "programs"

        intents = self._detect_intents(normalized)
        for intent in ("admission", "scholarship", "programs", "fees", "contact", "research", "campus"):
            if intent in intents:
                return intent
        if "diu" in normalized or "daffodil" in normalized:
            return "campus"
        return None

    def _is_freshness_sensitive_question(self, normalized_question: str) -> bool:
        return bool(re.search(
            r"\b(latest|recent|today|current|currently|now|new|upcoming|deadline|deadlines|notice|notices|announcement|announcements|this semester|next semester|upcoming semester)\b",
            normalized_question,
        ))

    def _is_program_cost_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        if not ("diu" in normalized or "daffodil" in normalized):
            return False
        has_cost_term = bool(re.search(r"\b(cost|fee|fees|tuition|payment|amount|price|expense|expenses)\b", normalized) or "how much" in normalized)
        has_program_term = bool(re.search(r"\b(graduate|graduation|degree|program|major|subject|study|studying|course|department|bsc|msc|bachelor|master|physics|cse|swe|software|computer|eee|mct)\b", normalized))
        return has_cost_term and has_program_term

    def _is_ranking_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return bool(re.search(r"\b(qs|rank|ranked|ranking|rankings)\b", normalized))

    def _is_broad_scholarship_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return bool(re.search(r"\b(scholarship|scholarships|waiver|waivers|financial aid|tuition aid)\b", normalized))

    def _is_fsit_department_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        names_fsit = "fsit" in normalized or "science information technology" in normalized or "science and information technology" in normalized
        asks_department_list = bool(re.search(r"\b(which|what|list|departments?|under|include|includes|comprise|comprises)\b", normalized))
        return names_fsit and asks_department_list

    def _is_curriculum_or_program_detail_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return bool(re.search(r"\b(curriculum|syllabus|course outline|course curriculum|courses?|program details?|credit|semester plan|lab|facilities|specialization|specialisations?|specializations?)\b", normalized))

    def _is_demandable_department_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        asks_choice = bool(re.search(r"\b(best|better|top|demand|demandable|market|career|job|scope|future|software engineering)\b", normalized))
        asks_program = bool(re.search(r"\b(department|departments|program|programs|course|subject|faculty|cse|swe|software|computer|it|ict)\b", normalized))
        return asks_choice and asks_program

    def _is_university_overview_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        names_diu = "diu" in normalized or "daffodil international university" in normalized
        asks_overview = bool(re.search(r"\b(what is|about|overview|introduction|profile|official|short|summary)\b", normalized))
        return names_diu and asks_overview

    def _is_official_overview_chunk(self, chunk: SiteChunk) -> bool:
        lowered_url = chunk.url.lower().rstrip("/")
        haystack = self._normalize_text(f"{chunk.title} {chunk.text}")
        return (
            lowered_url in {"https://daffodilvarsity.edu.bd", "https://daffodilvarsity.edu.bd/"}
            or "official daffodil international university homepage" in haystack
            or "vision" in haystack and "38 programs" in haystack and "6 faculties" in haystack
        )

    def _overview_evidence_score(self, match: ChunkMatch) -> float:
        lowered_url = match.chunk.url.lower().rstrip("/")
        score = match.score
        if lowered_url == "https://daffodilvarsity.edu.bd":
            score += 0.40
        if "official" in match.chunk.title.lower():
            score += 0.20
        return score

    def _chunk_mentions_rankings(self, chunk: SiteChunk) -> bool:
        haystack = self._normalize_text(f"{chunk.title} {chunk.url} {chunk.text}")
        return bool(re.search(r"\b(qs|rank|ranked|ranking|rankings)\b", haystack))

    def _ranking_evidence_score(self, match: ChunkMatch, question: str = "") -> float:
        haystack = f"{match.chunk.title} {match.chunk.url} {match.chunk.text}".lower()
        normalized_question = self._normalize_text(question)
        raw_question = str(question or "")
        wants_qs = "qs" in normalized_question or "topuniversities.com" in normalized_question
        wants_the = bool(re.search(r"\bTHE\b", raw_question) or re.search(r"\b(times higher education|impact)\b", normalized_question))
        years = [int(year) for year in re.findall(r"\b20(?:1[8-9]|2[0-9])\b", haystack)]
        latest_year = max(years) if years else 0
        score = match.score
        if "topuniversities.com" in haystack:
            score += 1.10 if wants_qs else 0.35
        elif wants_qs and "qs" not in haystack:
            score -= 0.70
        elif wants_qs and "qs" in haystack:
            score += 0.20
        if "timeshighereducation.com" in haystack:
            score += 1.10 if wants_the else 0.35
        elif wants_the and not ("times higher education" in haystack or re.search(r"\bthe\b", haystack)):
            score -= 0.70
        elif wants_the:
            score += 0.20
        if "wikipedia.org" in haystack:
            score += 0.08
        if "qs" in haystack:
            score += 0.16
        if "rankings" in match.chunk.url.lower():
            score += 0.14
        if "world university rankings" in haystack or "asia university rankings" in haystack:
            score += 0.08
        if "sustainability ranking" in haystack:
            score += 0.08
        if match.chunk.text.lower().lstrip().startswith("qs "):
            score += 0.14
        if latest_year >= 2026:
            score += 0.12
        if latest_year:
            score += min(max(latest_year - 2020, 0), 8) * 0.04
        if any(term in match.chunk.url.lower() for term in ("/event/", "video-gallery")):
            score -= 0.18
        if "news.daffodilvarsity.edu.bd" in match.chunk.url.lower() and (wants_qs or wants_the):
            score -= 0.35
        return score

    def _match_supports_intent(self, chunk: SiteChunk, intent: str | None) -> bool:
        if not intent:
            return not self._is_noisy_chunk(chunk)
        haystack = f"{chunk.title} {chunk.url} {chunk.text}".lower()
        if intent == "fees":
            return bool(re.search(r"\b(fee|fees|tuition|waiver|payment|cost)\b", haystack))
        if intent == "programs":
            return bool(re.search(r"\b(program|faculty|department|course|degree|credit|curriculum|cse|swe|mct|eee|bba|physics)\b", haystack))
        intent_terms = INTENT_PRIORITY.get(intent, set()) | INTENT_TERMS.get(intent, set())
        if any(str(term).lower() in haystack for term in intent_terms):
            return True
        return chunk.category == intent

    def _is_scholarship_detail_source(self, chunk: SiteChunk) -> bool:
        haystack = f"{chunk.url} {chunk.title} {chunk.text}".lower()
        if self._is_noisy_chunk(chunk):
            return False
        return (
            "daffodilvarsity.edu.bd/scholarship" in haystack
            or "daffodilvarsity.edu.bd/scholarships" in haystack
            or "tuition-fee-calculator" in haystack
            or bool(re.search(r"\b(result-based waiver|need-based|financial aid|merit-based|waiver and scholarship|scholarship opportunities)\b", haystack))
        )

    def _scholarship_evidence_score(self, match: ChunkMatch) -> float:
        url = match.chunk.url.lower()
        text = f"{match.chunk.title} {match.chunk.text}".lower()
        score = match.score
        if "/scholarships" in url:
            score += 0.80
        if "/scholarship" in url:
            score += 0.65
        if "tuition-fee-calculator" in url:
            score += 0.42
        if any(term in text for term in ("result-based waiver", "need-based", "financial aid", "merit-based", "80 %", "80%")):
            score += 0.25
        return score

    def _is_fsit_department_source(self, chunk: SiteChunk) -> bool:
        haystack = self._normalize_text(f"{chunk.title} {chunk.url} {chunk.text}")
        if self._is_noisy_chunk(chunk) or self._is_generic_program_faq(chunk):
            return False
        return (
            "faculty/fsit" in chunk.url.lower()
            or "admission/faculty/fsit" in chunk.url.lower()
            or "science information technology" in haystack
            or "science and information technology" in haystack
            or all(term in haystack for term in ("computing", "information", "system"))
            or all(term in haystack for term in ("information", "technology", "management"))
        )

    def _fsit_evidence_score(self, match: ChunkMatch) -> float:
        url = match.chunk.url.lower()
        haystack = self._normalize_text(f"{match.chunk.title} {match.chunk.text}")
        score = match.score
        if "webbackend.daffodilvarsity.edu.bd/faculty/fsit" in url:
            score += 0.90
        if "/admission/faculty/fsit" in url:
            score += 0.55
        if all(term in haystack for term in ("computing", "information", "system")):
            score += 0.30
        if all(term in haystack for term in ("information", "technology", "management")):
            score += 0.30
        if self._is_boilerplate_chunk(match.chunk):
            score -= 0.35
        return score

    def _is_requested_department_source(self, chunk: SiteChunk, department: str) -> bool:
        if self._is_noisy_chunk(chunk) or self._is_generic_program_faq(chunk):
            return False
        if self._is_boilerplate_chunk(chunk):
            return False
        haystack = self._normalize_text(f"{chunk.title} {chunk.url} {chunk.text}")
        aliases = DEPARTMENT_ALIASES.get(department, {department})
        mentions_alias = any(re.search(rf"\b{re.escape(alias)}\b", haystack) for alias in aliases | {department})
        url = chunk.url.lower()
        if re.search(r"/programs?\b", url) and "/department/" not in url:
            return False
        return (
            f"/department/{department}" in url
            or f"/lab-facilities/{department}" in url
            or mentions_alias and any(term in haystack for term in ("program", "curriculum", "course", "credit", "department", "faculty", "lab", "software", "computer"))
        )

    def _is_demand_program_source(self, chunk: SiteChunk) -> bool:
        if self._is_noisy_chunk(chunk) or self._is_generic_program_faq(chunk):
            return False
        if self._is_boilerplate_chunk(chunk):
            return False
        haystack = self._normalize_text(f"{chunk.title} {chunk.url} {chunk.text}")
        url = chunk.url.lower()
        if "/article/" in url or ("/admission/" in url and "faculty/fsit" not in url):
            return False
        names_relevant_program = bool(re.search(r"\b(cse|swe|software|computer|computing|information technology|information system|robotics|mechatronics|itm|cis)\b", haystack))
        has_demand_signal = bool(re.search(r"\b(industry|ict|it market|global it market|career|skilled manpower|job|demand|emerging technologies|data|ai|software professionals)\b", haystack))
        return (
            "webbackend.daffodilvarsity.edu.bd/faculty/fsit" in url
            or "/department/cse" in url
            or "/department/swe" in url
            or "/lab-facilities/swe" in url
            or (names_relevant_program and has_demand_signal)
        )

    def _academic_specificity_score(self, match: ChunkMatch, question: str, requested_department: str | None) -> float:
        url = match.chunk.url.lower()
        haystack = self._normalize_text(f"{match.chunk.title} {match.chunk.text}")
        score = match.score
        wants_curriculum = self._is_curriculum_or_program_detail_question(question)
        if requested_department:
            if f"/department/{requested_department}/program" in url:
                score += 1.10 if wants_curriculum else 0.90
            if f"/department/{requested_department}" in url:
                score += 1.00 if wants_curriculum else 0.75
            if f"/lab-facilities/{requested_department}" in url:
                score += 0.60 if wants_curriculum else 0.45
        if "webbackend.daffodilvarsity.edu.bd/faculty/fsit" in url:
            score += 0.35 if wants_curriculum else 0.65
        if any(term in haystack for term in ("curriculum", "course", "credit", "program", "software professionals", "global it market", "industry demands")):
            score += 0.25
        if self._is_generic_program_faq(match.chunk):
            score -= 0.75
        if self._is_boilerplate_chunk(match.chunk):
            score -= 0.35
        return score

    def _is_generic_program_faq(self, chunk: SiteChunk) -> bool:
        return False

    def _is_boilerplate_chunk(self, chunk: SiteChunk) -> bool:
        compact = self._normalize_text(chunk.text)
        if len(compact) < 60:
            return True
        boilerplate_hits = sum(
            1 for phrase in (
                "campus life in 60 seconds",
                "get a virtual tour",
                "visitor statistics",
                "future begins here",
                "copyright",
                "subscribe us",
                "social links",
            )
            if phrase in compact
        )
        return boilerplate_hits >= 3 and not re.search(
            r"\b(cse|swe|cis|itm|software engineering|computer science|computing|curriculum|course|credit|scholarship|waiver)\b",
            compact,
        )

    def _is_noisy_chunk(self, chunk: SiteChunk) -> bool:
        haystack = f"{chunk.url} {chunk.title}".lower()
        if any(host in haystack for host in ("timeshighereducation.com", "topuniversities.com", "wikipedia.org")):
            return False
        return any(term in haystack for term in (
            "news.daffodilvarsity",
            "research.daffodilvarsity",
            "alumni.daffodilvarsity",
            "parents.daffodilvarsity",
            "/alumni-detail",
            "/alumni-details",
            "/events",
            "media corner",
            "testimonial",
        ))

    def _is_eligibility_concern(self, question: str) -> bool:
        return bool(re.search(
            r"\b(fail|failed|failing|gpa|ssc|hsc|eligible|eligibility|requirement|requirements|minimum|criteria|qualify|transcript|certificate|documents?)\b",
            self._normalize_text(question),
        ))

    def _is_eligibility_chunk(self, chunk: SiteChunk) -> bool:
        haystack = f"{chunk.title} {chunk.url} {chunk.text}".lower()
        return bool(re.search(
            r"\b(fail|failed|failing|hsc fail|failed hsc|gpa|ssc|hsc|eligible|eligibility|minimum criteria|second division)\b",
            haystack,
        ))

    def _requested_department_alias(self, question: str) -> str | None:
        lowered = self._normalize_text(question)
        department_phrases = {
            "mct": ("mct", "multimedia", "creative technology", "multimedia creative technology"),
            "cse": ("cse", "computer science", "computer science engineering"),
            "swe": ("swe", "software engineering"),
            "cis": ("cis", "computing and information system", "computing information system"),
            "itm": ("itm", "information technology and management", "information technology management"),
            "eee": ("eee", "electrical electronic", "electrical and electronic"),
            "bba": ("bba", "business administration"),
        }
        for alias, phrases in department_phrases.items():
            if any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in phrases):
                return alias
        return None

    def _is_department_chunk(self, chunk: SiteChunk) -> bool:
        return self._department_alias_for_chunk(chunk) is not None

    def _department_alias_for_chunk(self, chunk: SiteChunk) -> str | None:
        haystack = self._normalize_text(f"{chunk.title} {chunk.url}")
        department_phrases = {
            "mct": ("department mct", "bsc in mct", "multimedia creative technology"),
            "cse": ("department cse", "computer science engineering"),
            "swe": ("department swe", "software engineering"),
            "cis": ("department cis", "computing information system"),
            "itm": ("department itm", "information technology management"),
            "eee": ("department eee", "electrical electronic engineering"),
            "bba": ("department bba", "business administration"),
        }
        for alias, phrases in department_phrases.items():
            if any(re.search(rf"\b{re.escape(phrase)}\b", haystack) for phrase in phrases):
                return alias
        return None

    def _dedupe_matches(self, matches: list[ChunkMatch]) -> list[ChunkMatch]:
        seen: set[str] = set()
        deduped: list[ChunkMatch] = []
        for match in matches:
            key = match.chunk.url or match.chunk.id
            if key in seen:
                continue
            seen.add(key)
            deduped.append(match)
        return deduped

    def _is_greeting(self, normalized: str) -> bool:
        return normalized in {"hi", "hello", "hey", "hola", "salam", "assalamu alaikum", "good morning", "good afternoon", "good evening"}

    def _is_casual_chat(self, normalized: str) -> bool:
        return normalized in {"thanks", "thank you", "thx", "ok", "okay", "bye", "goodbye"}

    def _is_diu_scoped(self, question: str, chat_history: list[dict[str, Any]] | None = None) -> bool:
        normalized = self._normalize_text(question)
        if self._is_greeting(normalized) or self._is_casual_chat(normalized) or normalized in {"huh", "what", "why", "how", "what about that"}:
            return True
        if any(term in normalized for term in ("diu", "daffodil", "university", "admission", "scholarship", "tuition", "campus", "faculty", "department", "program", "course", "ranking", "rankings", "ranked", "qs", "assistant", "ai", "how", "why", "what", "tell me")):
            return True
        if self._looks_like_followup(question) and chat_history:
            return bool(self._recent_followup_context(question, chat_history))
        return False

    # ------------------------------------------------------------------
    # Gemini helpers
    # ------------------------------------------------------------------

    def _gemini_is_configured(self) -> bool:
        return bool(self.gemini_client and getattr(self.gemini_client, "is_configured", False))

    def _merge_gemini_sources(
        self,
        source_urls: list[str] | None,
        source_titles: list[str] | None,
    ) -> tuple[list[str], list[str]]:
        urls: list[str] = []
        titles: list[str] = []
        seen: set[str] = set()

        def add(url: str | None, title: str | None) -> None:
            if not url or url in seen:
                return
            seen.add(url)
            urls.append(url)
            titles.append(title or url)

        for index, url in enumerate(source_urls or []):
            title = source_titles[index] if source_titles and index < len(source_titles) else None
            add(url, title)

        gemini_urls = getattr(self.gemini_client, "last_grounding_sources", []) or []
        gemini_titles = getattr(self.gemini_client, "last_grounding_titles", []) or []
        for index, url in enumerate(gemini_urls):
            title = gemini_titles[index] if index < len(gemini_titles) else None
            add(url, title)

        return urls, titles

    def _log_grounding_event(
        self,
        question: str,
        *,
        mode: str,
        raw_matches: list[ChunkMatch],
        selected_matches: list[ChunkMatch],
    ) -> None:
        intent = self._primary_intent(question)
        requested_department = self._requested_department_alias(question)
        if selected_matches:
            top_score = selected_matches[0].score
            if top_score < max(self.min_confidence, 0.12):
                log_event(
                    "retrieval_weak_match",
                    question=truncate_text(question),
                    normalized_question=normalize_question(question),
                    mode=mode,
                    intent=intent,
                    requested_department=requested_department,
                    raw_match_count=len(raw_matches),
                    selected_match_count=len(selected_matches),
                    top_score=round(top_score, 3),
                    top_source=selected_matches[0].chunk.url,
                )
            return

        log_event(
            "retrieval_miss",
            question=truncate_text(question),
            normalized_question=normalize_question(question),
            mode=mode,
            intent=intent,
            requested_department=requested_department,
            raw_match_count=len(raw_matches),
            selected_match_count=0,
            top_score=round(raw_matches[0].score, 3) if raw_matches else 0.0,
        )

    # ------------------------------------------------------------------
    # Simple error responses (only when Gemini can't be used at all)
    # ------------------------------------------------------------------

    def _empty_response(self, question: str, language: str) -> ChatResponse:
        return ChatResponse(
            question=question, answer="", category="system", source_url=None,
            language=language, confidence=0.0, found_match=False, used_gemini=False,
            matched_faq_id=None, source_urls=[], source_titles=[],
        )

    def _not_configured_response(self, question: str, language: str) -> ChatResponse:
        answer = (
            "The Gemini API key is not configured. Please set up GEMINI_API_KEY to enable the assistant."
            if language == "en"
            else "Gemini API key কনফিগার করা হয়নি। অনুগ্রহ করে GEMINI_API_KEY সেট করুন।"
        )
        return ChatResponse(
            question=question, answer=answer, category="system", source_url=None,
            language=language, confidence=0.0, found_match=False, used_gemini=False,
            matched_faq_id=None, source_urls=[], source_titles=[],
        )

    def _model_unavailable_response(self, question: str, language: str) -> ChatResponse:
        last_error = str(getattr(self.gemini_client, "last_error", "") or "")
        lowered_error = last_error.lower()
        retry_after_seconds = extract_retry_after_seconds(last_error)
        if "quota" in lowered_error or "billing" in lowered_error or "resource_exhausted" in lowered_error or "http 429" in lowered_error:
            if is_daily_free_tier_quota(last_error):
                answer = (
                    "The DIU Assistant service has reached its free daily usage limit for the current project. "
                    "Use an API key from a project with available quota, enable billing/increase quota, or wait for the daily reset."
                    if language == "en"
                    else "DIU Assistant service বর্তমান project-এর free daily usage limit-এ পৌঁছে গেছে। Available quota থাকা অন্য project-এর API key ব্যবহার করুন, billing/quota বাড়ান, অথবা daily reset হওয়া পর্যন্ত অপেক্ষা করুন।"
                )
            elif language == "en":
                answer = (
                    f"The DIU Assistant service is temporarily rate-limited. Try again in about {retry_after_seconds} seconds."
                    if retry_after_seconds
                    else "The DIU Assistant service is temporarily rate-limited. Please try again later."
                )
            else:
                answer = (
                    f"DIU Assistant service rate limit-এ পৌঁছেছে। প্রায় {retry_after_seconds} সেকেন্ড পর আবার চেষ্টা করুন。"
                    if retry_after_seconds
                    else "DIU Assistant service rate limit-এ পৌঁছেছে। অনুগ্রহ করে পরে আবার চেষ্টা করুন।"
                )
        elif "api_key_invalid" in lowered_error or "api key not valid" in lowered_error or "api key expired" in lowered_error:
            answer = (
                "The DIU Assistant service could not authenticate with the current API key. Please update the API key and try again."
                if language == "en"
                else "DIU Assistant service বর্তমান API key দিয়ে authenticate করতে পারেনি। অনুগ্রহ করে API key update করে আবার চেষ্টা করুন।"
            )
        else:
            answer = (
                "The DIU Assistant service didn't respond in time. Please try again in a moment."
                if language == "en"
                else "DIU Assistant service সময়মতো উত্তর দেয়নি। অনুগ্রহ করে একটু পর আবার চেষ্টা করুন।"
            )
        return ChatResponse(
            question=question, answer=answer, category="system", source_url=None,
            language=language, confidence=0.0, found_match=False, used_gemini=False,
            matched_faq_id=None, source_urls=[], source_titles=[],
        )

    def _extract_user_question_text(self, text: str) -> str:
        value = str(text or "").strip()
        if "Use this selected text from the current conversation" in value:
            return value
        match = re.search(r"\bUser question:\s*([\s\S]+)$", value, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return value

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _display_source_title(self, chunk: SiteChunk) -> str:
        lowered_url = chunk.url.lower()
        if "timeshighereducation.com" in lowered_url:
            return "Times Higher Education Profile"
        if "topuniversities.com" in lowered_url:
            return "QS TopUniversities Profile"
        if "wikipedia.org" in lowered_url:
            return "Wikipedia Overview"
        if "scholarship" in lowered_url:
            return "Scholarship Page"
        if "admission-process" in lowered_url or "admission-contact" in lowered_url:
            return "Admission Process"
        if lowered_url.rstrip("/") == "https://admission.daffodilvarsity.edu.bd":
            return "Admission Page"
        if "tuition-fee-calculator" in lowered_url:
            return "Tuition Fee Calculator"
        if "/faculty/engineering" in lowered_url:
            return "Engineering Programs"
        if "/faculty/social" in lowered_url:
            return "Arts & Social Programs"
        if "/department/mct" in lowered_url:
            return "MCT Department"
        title = unescape(chunk.title or "DIU Source").strip()
        return title or "DIU Source"

    # ------------------------------------------------------------------
    # RAG retrieval (kept — feeds context to Gemini)
    # ------------------------------------------------------------------

    def retrieve(self, question: str, *, top_k: int = 4) -> list[ChunkMatch]:
        query = (question or "").strip()
        if not query or not self.chunks:
            return []

        normalized_query = self._normalize_text(query)
        query_tokens = self._expanded_query_tokens(query)
        overlap_denominator = max(min(len(query_tokens), 6), 1)
        intents = self._detect_intents(query)
        matches: list[ChunkMatch] = []

        # Optimization: Pre-calculate phrases to avoid re-splitting inside the loop
        phrases = [part.strip() for part in normalized_query.split() if len(part.strip()) > 3] if normalized_query else []

        for chunk in self.chunks:
            token_overlap = len(query_tokens & chunk.tokens) / overlap_denominator if query_tokens else 0.0
            title_overlap = len(query_tokens & chunk.title_tokens) / overlap_denominator if query_tokens else 0.0
            
            # Fast filter: skip chunks with zero token overlap unless they are extremely small or special
            if token_overlap == 0 and title_overlap == 0:
                continue

            url_overlap = len(query_tokens & chunk.url_tokens) / overlap_denominator if query_tokens else 0.0
            
            # Skip expensive SequenceMatcher for full scan. 
            # Token overlap and phrase bonus are much faster and usually sufficient.
            contains_bonus = 0.18 if normalized_query and normalized_query in chunk.normalized_text else 0.0
            
            phrase_bonus = 0.0
            if phrases:
                phrase_hits = sum(1 for phrase in phrases if phrase in chunk.normalized_text or phrase in chunk.url.lower())
                phrase_bonus = min(phrase_hits * 0.04, 0.20)
            
            intent_boost = self._intent_score(chunk, intents)
            
            final_score = (
                (token_overlap * 0.50)
                + (title_overlap * 0.30)
                + (url_overlap * 0.15)
                + contains_bonus
                + phrase_bonus
                + intent_boost
            )
            
            if final_score > 0.05:
                matches.append(ChunkMatch(chunk=chunk, score=final_score))

        matches.sort(key=lambda item: item.score, reverse=True)
        unique_matches = self._diversify_matches(matches, top_k=top_k)
        
        # New: Merge consecutive chunks from the same URL to provide continuous context
        return self._merge_consecutive_chunks(unique_matches)

    def _merge_consecutive_chunks(self, matches: list[ChunkMatch]) -> list[ChunkMatch]:
        if not matches:
            return []
        
        merged: list[ChunkMatch] = []
        by_url: dict[str, list[ChunkMatch]] = {}
        
        for m in matches:
            by_url.setdefault(m.chunk.url, []).append(m)
            
        for url, chunk_list in by_url.items():
            if len(chunk_list) <= 1:
                merged.append(chunk_list[0])
                continue
                
            # Sort by chunk ID to ensure order
            chunk_list.sort(key=lambda x: x.chunk.id)
            
            base = chunk_list[0]
            current_text = base.chunk.text
            
            for next_match in chunk_list[1:]:
                # If they are very close in ID, they are likely neighbors
                current_text += "\n\n" + next_match.chunk.text
                
            base.chunk.text = current_text
            merged.append(base)
            
        return sorted(merged, key=lambda x: x.score, reverse=True)

    def detect_language(self, text: str) -> str:
        bangla_chars = len(re.findall(r"[\u0980-\u09FF]", text))
        english_chars = len(re.findall(r"[A-Za-z]", text))
        if bangla_chars >= 2 and bangla_chars >= max(1, english_chars * 0.25):
            return "bn"
        return "en"

    # ------------------------------------------------------------------
    # Index loading
    # ------------------------------------------------------------------

    def _load_index_if_available(self) -> None:
        if not self.site_index_path.exists():
            self.index_metadata = {}
            self.chunks = []
            return

        payload = json.loads(self.site_index_path.read_text(encoding="utf-8"))
        self.index_metadata = payload.get("metadata", {})
        self.chunks = []
        for item in payload.get("chunks", []):
            title = item.get("title", "")
            text = item.get("text", "")
            normalized_text = self._normalize_text(f"{title} {text}")
            self.chunks.append(
                SiteChunk(
                    id=item["id"], url=item["url"], title=title, text=text,
                    normalized_text=normalized_text,
                    tokens=self._tokenize(text),
                    title_tokens=self._tokenize(title),
                    url_tokens=self._tokenize(item["url"]),
                )
            )

    # ------------------------------------------------------------------
    # Query context / follow-up handling
    # ------------------------------------------------------------------

    def _contextualize_query(self, question: str, chat_history: list[dict[str, Any]] | None) -> str:
        clean_question = str(question or "").strip()
        if not clean_question or not chat_history or not self._looks_like_followup(clean_question):
            return clean_question

        topic_index = self._latest_substantive_user_topic(chat_history)
        scoped_history = chat_history[topic_index:] if topic_index >= 0 else chat_history
        session_topic = ""
        if topic_index >= 0:
            session_topic = self._history_excerpt_for_retrieval(str(chat_history[topic_index].get("content", "")).strip())

        recent_context = self._recent_followup_context(clean_question, scoped_history)
        if not session_topic and not recent_context:
            return clean_question

        return (
            f"{clean_question}\n\n"
            f"Session topic: {session_topic or recent_context}\n"
            f"Relevant recent context: {recent_context}"
        )

    def _latest_substantive_user_topic(self, chat_history: list[dict[str, Any]]) -> int:
        for index in range(len(chat_history) - 1, -1, -1):
            message = chat_history[index]
            if message.get("role") != "user":
                continue
            content = str(message.get("content", "")).strip()
            if content and not self._looks_like_followup(content):
                return index

        for index in range(len(chat_history) - 1, -1, -1):
            message = chat_history[index]
            if message.get("role") == "user" and str(message.get("content", "")).strip():
                return index

        return -1

    def _recent_followup_context(self, question: str, chat_history: list[dict[str, Any]]) -> str:
        normalized_question = self._normalize_text(question)
        excerpts: list[str] = []
        for message in chat_history[-8:]:
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = str(message.get("content", "")).strip()
            if not content or self._normalize_text(content) == normalized_question:
                continue
            excerpt = self._history_excerpt_for_retrieval(content)
            if excerpt:
                excerpts.append(excerpt)
        return " ".join(excerpts[-4:])

    def _history_excerpt_for_retrieval(self, content: str) -> str:
        cleaned = re.sub(r"`([^`]+)`", r"\1", content)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"[*_#>|-]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:320]

    def _looks_like_followup(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        tokens = normalized.split()
        if not normalized:
            return False
        vague_followups = (
            "more",
            "more detail",
            "more details",
            "more detailed",
            "details",
            "detail please",
            "explain more",
            "tell me more",
            "elaborate",
            "chart",
            "table",
            "summarize it",
            "summarise it",
        )
        if len(tokens) <= 4 and any(phrase in normalized for phrase in vague_followups):
            return True
        if len(tokens) <= 2:
            return any(t in {"it", "this", "that", "them", "those", "these", "same", "related"} for t in tokens)
        if len(tokens) <= 5 and any(t in {"it", "this", "that", "them", "those", "these", "same", "related"} for t in tokens):
            return True
        followup_starters = (
            "what about", "how about", "and", "also", "then", "that", "this",
            "it", "them", "those", "these", "same", "related", "for this",
            "for that", "in this", "in that", "আর", "তাহলে", "এটা", "ওটা",
        )
        if normalized.startswith(followup_starters):
            return True
        return len(tokens) <= 10 and any(
            t in {"it", "this", "that", "them", "those", "these", "same", "related"} for t in tokens
        )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _unique_urls(self, matches: list[ChunkMatch]) -> list[str]:
        seen: set[str] = set()
        urls: list[str] = []
        for match in matches:
            if match.chunk.url not in seen:
                seen.add(match.chunk.url)
                urls.append(match.chunk.url)
        return urls

    def _unique_titles(self, matches: list[ChunkMatch]) -> list[str]:
        seen: set[str] = set()
        titles: list[str] = []
        for match in matches:
            if match.chunk.url not in seen:
                seen.add(match.chunk.url)
                titles.append(self._display_source_title(match.chunk))
        return titles

    def _normalize_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^0-9a-z\u0980-\u09ff\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _tokenize(self, text: str) -> set[str]:
        normalized = self._normalize_text(text)
        language = self.detect_language(normalized)
        stopwords = STOPWORDS_BN if language == "bn" else STOPWORDS_EN
        return {token for token in normalized.split() if token and token not in stopwords}

    def _expanded_query_tokens(self, text: str) -> set[str]:
        tokens = self._tokenize(text)
        lowered = self._normalize_text(text)
        expanded = set(tokens)
        for values in INTENT_TERMS.values():
            if any(term in lowered for term in values):
                expanded.update(values)
                for term in values:
                    expanded.update(self._tokenize(term))
        for alias, values in DEPARTMENT_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                expanded.update(values)
                for term in values:
                    expanded.update(self._tokenize(term))
        for phrase, values in QUERY_PHRASE_ALIASES.items():
            if phrase in lowered:
                expanded.update(values)
                for term in values:
                    expanded.update(self._tokenize(term))
        return expanded

    def _detect_intents(self, text: str) -> set[str]:
        lowered = self._normalize_text(text)
        matched: set[str] = set()
        for intent, values in INTENT_TERMS.items():
            if any(term in lowered for term in values):
                matched.add(intent)
        return matched

    def _intent_score(self, chunk: SiteChunk, intents: set[str]) -> float:
        if not intents:
            return 0.0
        lowered_url = chunk.url.lower()
        lowered_title = chunk.title.lower()
        score = 0.0
        for intent in intents:
            priority_terms = INTENT_PRIORITY.get(intent, set())
            if any(term in lowered_url or term in lowered_title for term in priority_terms):
                score += 0.16
            preferred_hosts = INTENT_HOST_PREFERENCE.get(intent)
            if preferred_hosts:
                if any(host in lowered_url for host in preferred_hosts):
                    score += 0.05
                else:
                    score -= 0.04
        return max(min(score, 0.26), -0.12)

    def _diversify_matches(self, matches: list[ChunkMatch], *, top_k: int) -> list[ChunkMatch]:
        chosen: list[ChunkMatch] = []
        seen_urls: set[str] = set()
        for match in matches:
            if match.chunk.url not in seen_urls:
                chosen.append(match)
                seen_urls.add(match.chunk.url)
            if len(chosen) >= top_k:
                return chosen
        for match in matches:
            if match not in chosen:
                chosen.append(match)
            if len(chosen) >= top_k:
                break
        return chosen
