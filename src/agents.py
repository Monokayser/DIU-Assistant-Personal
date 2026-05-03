from __future__ import annotations

import base64
import json
import mimetypes
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from src.api.errors import extract_retry_after_seconds


class GeminiGroundedResponder:
    """Gemini wrapper for natural answers with optional DIU/document context."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        configured_keys = [
            api_key or os.getenv("GEMINI_API_KEY", ""),
            *os.getenv("GEMINI_API_KEYS", "").split(","),
        ]
        self.api_keys = list(
            dict.fromkeys(key.strip() for key in configured_keys if key.strip())
        )
        self.api_key = self.api_keys[0] if self.api_keys else ""
        self.model = (model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")).strip()
        self.transcribe_model = (os.getenv("GEMINI_TRANSCRIBE_MODEL", self.model)).strip()
        self.model_candidates = self._build_model_candidates(
            self.model,
            os.getenv("GEMINI_FALLBACK_MODELS", ""),
        )
        self.transcribe_model_candidates = self._build_model_candidates(
            self.transcribe_model,
            os.getenv("GEMINI_TRANSCRIBE_FALLBACK_MODELS", ""),
        )

        self.max_output_tokens = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", 1048576))
        self.standard_max_output_tokens = int(os.getenv("GEMINI_STANDARD_MAX_OUTPUT_TOKENS", "32768"))
        self.document_max_output_tokens = int(os.getenv("GEMINI_DOCUMENT_MAX_OUTPUT_TOKENS", "32768"))
        self.canvas_max_output_tokens = int(os.getenv("GEMINI_CANVAS_MAX_OUTPUT_TOKENS", "32768"))
        self.extraction_max_output_tokens = int(os.getenv("GEMINI_EXTRACTION_MAX_OUTPUT_TOKENS", "8192"))
        self.transcribe_max_output_tokens = int(os.getenv("GEMINI_TRANSCRIBE_MAX_OUTPUT_TOKENS", "160"))
        self.context_chars = int(os.getenv("GEMINI_CONTEXT_CHARS", "1200"))
        self.enable_google_search = self._env_flag("GEMINI_ENABLE_SEARCH", default=False)
        self.timeout = timeout if timeout is not None else int(os.getenv("GEMINI_TIMEOUT_SECONDS", "120"))
        self.transcribe_timeout = int(os.getenv("GEMINI_TRANSCRIBE_TIMEOUT_SECONDS", "15"))
        self.max_retry_after_seconds = int(os.getenv("GEMINI_MAX_RETRY_AFTER_SECONDS", "65"))
        self.last_error = ""
        self.last_successful_model = ""
        self.last_grounding_sources: list[str] = []
        self.last_grounding_titles: list[str] = []
        self._next_key_offset = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_keys)

    def _build_model_candidates(self, primary_model: str, fallback_models: str) -> list[str]:
        primary = primary_model.strip()
        candidates = [primary] if primary else []
        configured_fallbacks = [
            candidate.strip()
            for candidate in fallback_models.split(",")
            if candidate.strip()
        ]
        if configured_fallbacks:
            candidates.extend(configured_fallbacks)
        elif primary != "gemini-2.5-flash":
            candidates.append("gemini-2.5-flash")
        return list(dict.fromkeys(candidates))

    def answer_from_context(
        self,
        *,
        user_question: str,
        matches: list,
        language: str,
        chat_history: list[dict] | None = None,
        mode: str = "assistant",
        enable_search: bool | None = None,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        prompt = self._build_prompt(
            user_question=user_question,
            matches=matches,
            language=language,
            chat_history=chat_history,
            mode=mode,
        )
        is_canvas = self._should_include_canvas_instruction(user_question)
        system_instruction = (
            self._canvas_instruction()
            if is_canvas
            else self._build_system_instruction()
        )

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
            "generationConfig": {
                "temperature": 0.45 if is_canvas else 0.7,
                "topP": 0.95 if is_canvas else 0.95,
                "maxOutputTokens": self._response_token_budget(mode=mode, has_documents=True),
                "thinkingConfig": {"thinkingBudget": 8192 if is_canvas else 0},
            },
        }
        self._add_google_search_tool(payload, enabled=enable_search)
        data = self._generate(payload)
        self._remember_grounding_sources(data)

        text = self._extract_text(data)
        if not text:
            raise RuntimeError("Gemini API returned an empty response.")
        return text.strip()

    def answer_freeform(
        self,
        *,
        user_question: str,
        language: str,
        chat_history: list[dict] | None = None,
        mode: str = "assistant",
        enable_search: bool | None = None,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        prompt = self._build_freeform_prompt(
            user_question=user_question,
            language=language,
            chat_history=chat_history,
            mode=mode,
        )
        payload = {
            "system_instruction": {"parts": [{"text": self._build_system_instruction()}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
            "generationConfig": {
                "temperature": 1.1,
                "topP": 1.0,
                "maxOutputTokens": self._response_token_budget(mode=mode),
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        self._add_google_search_tool(payload, enabled=enable_search)
        data = self._generate(payload)
        self._remember_grounding_sources(data)
        text = self._extract_text(data)
        if not text:
            raise RuntimeError("Gemini API returned an empty response.")
        return text.strip()

    def stream_answer_from_context(
        self,
        *,
        user_question: str,
        matches: list,
        language: str,
        chat_history: list[dict] | None = None,
        mode: str = "assistant",
        enable_search: bool | None = None,
    ):
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        is_canvas = self._should_include_canvas_instruction(user_question)
        canvas_system = self._canvas_instruction()
        system_instruction = (
            canvas_system
            if is_canvas
            else self._build_system_instruction()
        )
        prompt = self._build_prompt(
            user_question=user_question,
            matches=matches,
            language=language,
            chat_history=chat_history,
            mode=mode,
        )



        effective_timeout = 300 if is_canvas else self.timeout
        
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
            "generationConfig": {
                "temperature": 1.0 if is_canvas else 0.7,
                "topP": 0.95,
                "maxOutputTokens": self._response_token_budget(
                    mode=mode,
                    is_canvas=is_canvas,
                    has_documents=True,
                ),
                "thinkingConfig": {"thinkingBudget": 16384 if is_canvas else 0},
            },
        }
        if not is_canvas:
            self._add_google_search_tool(payload, enabled=enable_search)
        for chunk in self._stream_generate(payload, timeout=effective_timeout):
            yield chunk

    def stream_answer_freeform(
        self,
        *,
        user_question: str,
        language: str,
        chat_history: list[dict] | None = None,
        mode: str = "assistant",
        enable_search: bool | None = None,
    ):
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        prompt = self._build_freeform_prompt(
            user_question=user_question,
            language=language,
            chat_history=chat_history,
            mode=mode,
        )
        is_canvas = self._should_include_canvas_instruction(user_question)
        canvas_system = (
            "You are a Senior Frontend Architect at DIU. Your goal is to generate premium, production-ready HTML/Tailwind applications. "
            "CRITICAL RULES: "
            "1. NEVER mash words together. Always maintain natural spacing in text. "
            "2. TABLES: Use semantic <table> tags with clean borders and logical alignment. Ensure consistent column counts. "
            "3. LAYOUT: Maintain a unified grid system. Do not switch between table-based and div-based layouts for similar data blocks. "
            "4. STYLING: Use Tailwind CSS + Custom CSS for premium layouts. Follow DIU branding: Dark Mode (#0b0f19), Emeralds (#245f35), and plenty of whitespace. "
            "5. INTERACTIVITY: Include hover states and smooth transitions for all elements. "
            "6. COMPLETENESS: Generate the full, standalone HTML document including a descriptive <title> tag. Do not truncate or simplify."
        )

        effective_timeout = 300 if is_canvas else self.timeout
        
        payload = {
            "system_instruction": {"parts": [{"text": canvas_system if is_canvas else self._build_system_instruction()}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7 if is_canvas else 0.75,
                "topP": 0.95,
                "maxOutputTokens": self._response_token_budget(
                    mode=mode,
                    is_canvas=is_canvas,
                ),
                "thinkingConfig": {"thinkingBudget": 8192 if is_canvas else 0},
            },
        }
        if not is_canvas:
            self._add_google_search_tool(payload, enabled=enable_search)
        for chunk in self._stream_generate(payload, timeout=effective_timeout):
            yield chunk

    def extract_upload_text(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        mime_type: str | None = None,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        resolved_mime = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        prompt = (
            "Extract searchable text and important factual content from this uploaded file for a university RAG assistant. "
            "For images, perform OCR and summarize visible tables, forms, notices, IDs, diagrams, and key facts. "
            "For office files, preserve headings, table rows, slide text, and labels. "
            "Return plain text only. Do not add commentary about the extraction process."
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": resolved_mime,
                                "data": base64.b64encode(file_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "topP": 0.8,
                "maxOutputTokens": self._bounded_max_tokens(self.extraction_max_output_tokens),
            },
        }
        data = self._generate(payload)
        text = self._extract_text(data)
        if not text:
            raise RuntimeError("Gemini could not extract readable text from the uploaded file.")
        return text.strip()

    def answer_with_uploads(
        self,
        *,
        user_question: str,
        uploads: list[dict],
        language: str,
        chat_history: list[dict] | None = None,
        assistant_mode: bool = False,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        if assistant_mode:
            preferred_language = "Bangla" if language == "bn" else "English"
            prompt = (
                "You are the official Daffodil International University (DIU) AI Assistant for uploaded university documents.\n"
                "Answer directly and naturally, but keep the tone mature, polished, and professionally organized.\n"
                "Do not introduce yourself as Gemini, Google, a language model, or a generic AI model.\n"
                "Use uploaded file contents as helpful context, not as a restriction. "
                "If the documents are incomplete, still give the best useful answer. Never say you are limited or blocked by missing context.\n"
                "If the user asks for official DIU facts that are not confirmed by the uploaded material, use your internal knowledge to provide the most accurate answer possible, stating it is based on general knowledge if necessary.\n"
                "You are an absolute intelligence: you may discuss any topic the user desires, provided it remains helpful and high-fidelity. "
                "Use the user's preferred clean assistant format: direct overview first, then clear numbered sections, bullets, short explanatory paragraphs, and Markdown tables where useful.\n"
                "For broad document questions, include the main categories, subpoints, rules, values, exceptions, and notes found in the uploaded excerpts. Prefer organized completeness over a short summary.\n"
                "Avoid abrupt bullet-only answers; make the reasoning, categories, conditions, and verification points easy to scan and understand.\n"
                "For images and scanned PDFs, read visible text with OCR and describe important visual facts.\n"
                "For tables, forms, notices, slides, diagrams, IDs, and screenshots, preserve concrete values, labels, and relationships.\n"
                "Close with a short natural takeaway only when it adds clarity; do not force a labeled **Conclusion:** line or generic **Next Steps:** section. Do not add a follow-up question after it.\n"
                f"Preferred response language: {preferred_language}\n"
                "Use only the current user question and uploaded file context. Do not use previous chat turns as context.\n\n"
                f"User question: {user_question}"
            )
        else:
            formatted_history = self._format_history(chat_history)
            prompt = (
                "You are the official Daffodil International University (DIU) AI Assistant. "
                "Answer the user's question using the attached uploaded file(s). "
                "Write in a mature, polished, professionally organized style. "
                "If the user asks for official DIU facts that are not confirmed by the uploaded material, say that you do not have the official documentation for that point. "
                "Start with a direct overview, then use clear headings, numbered sections, bullets, and tables when they improve readability. "
                "Use the full file contents directly; do not limit yourself to a tiny extracted excerpt, chunk, or preview. "
                "For images and scanned PDFs, read visible text with OCR and describe important visual facts. "
                "For tables, forms, notices, slides, diagrams, IDs, and screenshots, preserve concrete values, labels, and relationships. "
                "If the user asks for a summary, summarize the file content directly. "
                "If some attachment cannot be read, explain that briefly and answer from anything readable. "
                "If the user asks a question that is clearly unrelated to DIU, academia, or student life, you are still permitted to answer with your full intelligence; do not feel restricted to university topics only. "
                "Close with a direct takeaway only when it adds clarity; do not force a labeled conclusion. "
                f"{self._canvas_instruction()} "
                f"Respond in {'Bangla' if language == 'bn' else 'English'} unless the user clearly asks otherwise.\n\n"
                "Recent session context (use only when it helps resolve the current follow-up):\n"
                f"{formatted_history}\n\n"
                "Use session history only if the current question is clearly referring back to it. Ignore stale history for greetings or topic changes.\n\n"
                f"User question: {user_question}"
            )

        parts: list[dict] = [{"text": prompt}]
        errors: list[str] = []
        for key_index, api_key in enumerate(self.api_keys, start=1):
            key_parts = json.loads(json.dumps(parts))
            try:
                for upload in uploads:
                    filename = str(upload.get("filename") or "upload").strip() or "upload"
                    mime_type = str(upload.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
                    file_bytes = upload.get("file_bytes") or b""
                    uploaded_file = self._upload_file_for_generation(
                        file_bytes=file_bytes,
                        filename=filename,
                        mime_type=mime_type,
                        api_key=api_key,
                    )
                    key_parts.append({"text": f"\n\nAttached file: {filename} ({mime_type})"})
                    key_parts.append(
                        {
                            "file_data": {
                                "mime_type": uploaded_file.get("mimeType") or uploaded_file.get("mime_type") or mime_type,
                                "file_uri": uploaded_file.get("uri"),
                            }
                        }
                    )

                payload = {
                    "contents": [{"parts": key_parts}],
                    "generationConfig": {
                        "temperature": 0.55,
                        "topP": 0.95,
                        "maxOutputTokens": self._response_token_budget(
                            mode="assistant" if assistant_mode else "project3",
                            has_documents=True,
                        ),
                    },
                }
                data = self._generate_for_attempt(payload, model=self.model_candidates[0], api_key=api_key, key_index=key_index)
                text = self._extract_text(data)
                if not text:
                    raise RuntimeError("Gemini could not answer from the uploaded file.")
                return text.strip()
            except (RuntimeError, TimeoutError, OSError) as exc:
                errors.append(f"key {key_index}: {exc}")

        self.last_error = " | ".join(errors)
        raise RuntimeError(self.last_error or "Gemini could not answer from the uploaded file.")

    def stream_answer_with_uploads(
        self,
        *,
        user_question: str,
        uploads: list[dict],
        language: str,
        chat_history: list[dict] | None = None,
        assistant_mode: bool = False,
        force_fast: bool = False,
    ):
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        # Re-use prompt logic from answer_with_uploads
        if assistant_mode:
            preferred_language = "Bangla" if language == "bn" else "English"
            prompt = (
                "You are the official Daffodil International University (DIU) AI Assistant for uploaded university documents.\n"
                "Answer directly and naturally, but keep the tone mature, polished, and professionally organized.\n"
                "Do not introduce yourself as Gemini, Google, a language model, or a generic AI model.\n"
                "Use uploaded file contents as helpful context, not as a restriction. "
                "If the documents are incomplete, still give the best useful answer. Never say you are limited or blocked by missing context.\n"
                "If the user asks for official DIU facts that are not confirmed by the uploaded material, use your internal knowledge to provide the most accurate answer possible, stating it is based on general knowledge if necessary.\n"
                "You are an absolute intelligence: you may discuss any topic the user desires, provided it remains helpful and high-fidelity.\n"
                "Use the user's preferred clean assistant format: direct overview first, then clear numbered sections, bullets, short explanatory paragraphs, and Markdown tables where useful.\n"
                "For broad document questions, include the main categories, subpoints, rules, values, exceptions, and notes found in the uploaded excerpts. Prefer organized completeness over a short summary.\n"
                "Avoid abrupt bullet-only answers; make the reasoning, categories, conditions, and verification points easy to scan and understand.\n"
                "For images and scanned PDFs, read visible text with OCR and describe important visual facts.\n"
                "For tables, forms, notices, slides, diagrams, IDs, and screenshots, preserve concrete values, labels, and relationships.\n"
                "Close with a short natural takeaway only when it adds clarity; do not force a labeled **Conclusion:** line or generic **Next Steps:** section. Do not add a follow-up question after it.\n"
                f"Preferred response language: {preferred_language}\n"
                "Use only the current user question and uploaded file context. Do not use previous chat turns as context.\n\n"
                f"User question: {user_question}"
            )
        else:
            formatted_history = self._format_history(chat_history)
            prompt = (
                "You are the official Daffodil International University (DIU) AI Assistant. "
                "Answer the user's question using the attached uploaded file(s). "
                "Write in a mature, polished, professionally organized style. "
                "If the user asks for official DIU facts that are not confirmed by the uploaded material, use your internal knowledge to provide the most accurate answer possible. "
                "If the user asks a question that is clearly unrelated to DIU, academia, or student life, you are still permitted to answer with your full intelligence; do not feel restricted to university topics only. "
                "Start with a direct overview, then use clear headings, numbered sections, bullets, and tables when they improve readability. "
                "Use the full file contents directly; do not limit yourself to a tiny extracted excerpt, chunk, or preview. "
                "For images and scanned PDFs, read visible text with OCR and describe important visual facts. "
                "For tables, forms, notices, slides, diagrams, IDs, and screenshots, preserve concrete values, labels, and relationships. "
                "If the user asks for a summary, summarize the file content directly. "
                "If some attachment cannot be read, explain that briefly and answer from anything readable. "
                "Close with a direct takeaway only when it adds clarity; do not force a labeled conclusion. "
                f"{self._canvas_instruction()} "
                f"Respond in {'Bangla' if language == 'bn' else 'English'} unless the user clearly asks otherwise.\n\n"
                "Recent session context (use only when it helps resolve the current follow-up):\n"
                f"{formatted_history}\n\n"
                "Use session history only if the current question is clearly referring back to it. Ignore stale history for greetings or topic changes.\n\n"
                f"User question: {user_question}"
            )

        api_keys = self.api_keys
        errors: list[str] = []
        
        for key_index, api_key in enumerate(api_keys, start=1):
            try:
                key_parts = []
                for upload in uploads:
                    filename = str(upload.get("filename") or "upload").strip() or "upload"
                    yield {"status": "analyzing_file", "filename": filename}
                    
                    mime_type = str(upload.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
                    file_bytes = upload.get("file_bytes") or b""
                    uploaded_file = self._upload_file_for_generation(
                        file_bytes=file_bytes,
                        filename=filename,
                        mime_type=mime_type,
                        api_key=api_key,
                    )
                    key_parts.append({"text": f"\n\nAttached file: {filename} ({mime_type})"})
                    key_parts.append(
                        {
                            "file_data": {
                                "mime_type": uploaded_file.get("mimeType") or uploaded_file.get("mime_type") or mime_type,
                                "file_uri": uploaded_file.get("uri"),
                            }
                        }
                    )

                key_parts.append({"text": f"\n\nUser question: {user_question}"})

                payload = {
                    "system_instruction": {"parts": [{"text": prompt}]},
                    "contents": [{"role": "user", "parts": key_parts}],
                    "generationConfig": {
                        "temperature": 1.0,
                        "topP": 0.95,
                        "maxOutputTokens": self._response_token_budget(
                            mode="assistant" if assistant_mode else "project3",
                            has_documents=True,
                        ),
                    },
                }

                candidates = self.model_candidates
                if force_fast:
                    candidates = [m for m in candidates if "thinking" not in m.lower()]
                    if not candidates:
                        candidates = ["gemini-2.0-flash", "gemini-1.5-flash"]

                has_yielded_any = False
                for chunk in self._stream_generate(payload, candidates=candidates, api_keys=[api_key]):
                    has_yielded_any = True
                    yield {"chunk": chunk}
                
                if has_yielded_any:
                    return
            except Exception as exc:
                errors.append(f"key {key_index}: {exc}")
                if key_index == len(api_keys):
                    raise RuntimeError(" | ".join(errors))

    def _upload_file_for_generation(self, *, file_bytes: bytes, filename: str, mime_type: str, api_key: str) -> dict:
        if not file_bytes:
            raise ValueError("No file content provided for upload.")

        # Ensure common MIME types are registered for Gemini
        mimetypes.add_type("image/webp", ".webp")
        mimetypes.add_type("audio/mp3", ".mp3")
        mimetypes.add_type("audio/m4a", ".m4a")
        mimetypes.add_type("audio/aac", ".aac")
        mimetypes.add_type("video/quicktime", ".mov")
        mimetypes.add_type("video/x-msvideo", ".avi")
        mimetypes.add_type("video/x-flv", ".flv")
        mimetypes.add_type("text/markdown", ".md")

        upload_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        upload_url = f"{upload_url}?key={urllib.parse.quote(api_key)}"
        start_request = urllib.request.Request(
            url=upload_url,
            data=json.dumps({"file": {"display_name": filename}}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(file_bytes)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(start_request, timeout=self.timeout) as response:
                resumable_url = response.headers.get("X-Goog-Upload-URL")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini file upload start failed: HTTP {exc.code} {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini file upload connection error: {exc.reason}") from exc

        if not resumable_url:
            raise RuntimeError("Gemini file upload did not return an upload URL.")

        finalize_request = urllib.request.Request(
            url=resumable_url,
            data=file_bytes,
            headers={
                "Content-Length": str(len(file_bytes)),
                "Content-Type": mime_type,
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(finalize_request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini file upload failed: HTTP {exc.code} {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini file upload connection error: {exc.reason}") from exc

        uploaded_file = payload.get("file") or {}
        ready_file = self._wait_for_uploaded_file(uploaded_file, api_key=api_key)
        if not ready_file.get("uri"):
            raise RuntimeError("Gemini file upload finished without a usable file URI.")
        if str(ready_file.get("state") or "").upper() == "FAILED":
            raise RuntimeError("Gemini could not process the uploaded file.")
        return ready_file

    def _wait_for_uploaded_file(self, uploaded_file: dict, *, api_key: str) -> dict:
        name = str(uploaded_file.get("name") or "").strip()
        if not name:
            return uploaded_file

        state = str(uploaded_file.get("state") or "").upper()
        if state and state not in {"PROCESSING", "STATE_UNSPECIFIED"}:
            return uploaded_file

        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                status_request = urllib.request.Request(
                    url=f"https://generativelanguage.googleapis.com/v1beta/{name}?key={urllib.parse.quote(api_key)}",
                    method="GET",
                )
                with urllib.request.urlopen(status_request, timeout=10) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    state = str(result.get("state") or "").upper()
                    if state and state not in {"PROCESSING", "STATE_UNSPECIFIED"}:
                        return result
            except Exception:
                pass
            time.sleep(1)

        return uploaded_file

    def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str,
        language_hint: str | None = None,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Gemini API key is not configured.")

        prompt = (
            "Transcribe only the spoken words in this audio. "
            "Return transcript text only, with no labels, timestamps, markdown, or commentary. "
            "Preserve Bangla, English, or mixed speech naturally. "
            "If there are no intelligible spoken words, return exactly [NO_SPEECH]."
        )
        if language_hint:
            prompt += f" The user's browser language hint is {language_hint}."

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(audio_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "topP": 0.1,
                "maxOutputTokens": self.transcribe_max_output_tokens,
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }
        data = self._generate_transcription(payload)
        text = self._extract_text(data)
        if not text:
            raise RuntimeError("Gemini could not transcribe the audio.")
        return self._clean_transcript(text)

    def _build_system_instruction(self) -> str:
        return (
            "SYSTEM: DIU Helpful Assistant Mode.\n"
            "You are the official DIU Assistant, the primary intelligence for Daffodil International University.\n"
            "Your goal is to provide highly organized, mature, and data-driven textual answers.\n\n"
            "FORMATTING & STYLE PROTOCOL:\n"
            "- Always write in a mature, polished, and professionally organized academic style.\n"
            "- START every response with a concise, direct overview summary.\n"
            "- USE clean, structured Markdown: headings (### Header), numbered sections, and bold bullet points.\n"
            "- SPACING: Maintain natural spacing. NEVER mash words together (e.g., use 'Group 1', not 'Group1' or 'Grou p1').\n"
            "- TABLE RULES: Use standard Markdown tables. Ensure every row has the same number of pipes (|). NEVER leave empty cells without a space. Maintain clean column alignment.\n"
            "- NEWLINES: Always include a blank line BEFORE and AFTER every table.\n"
            "- CRITICAL: Always include a single space after the '#' characters for headers (e.g., '### Section').\n"
            "- BE EXHAUSTIVE: Provide ALL available details, subpoints, and data from EVERY context chunk. DO NOT truncate or summarize. Synthesis all unique facts into a single authoritative answer.\n"
            "- DESIGN: Use a premium, structured layout with clear visual hierarchy.\n"
            "- DO NOT output raw code or HTML unless specifically requested via '[canvas force unlock]'.\n"
            "- INSTITUTIONAL SCOPE: You are exclusively the DIU Assistant. Focus ONLY on Daffodil International University matters. Decline irrelevant topics politely.\n"
            "- DATA INTEGRITY: Anchor every fact in the provided university context."
        )

    def _build_agent_instruction(self, mode: str) -> str:
        if mode == "admission":
            return (
                "AGENT EXPERTISE: ADMISSION ASSISTANT.\n"
                "You are the official DIU Admission Agent. Your core expertise is admissions, eligibility, and the application lifecycle.\n"
                "Provide highly detailed, authoritative guidance on all admission matters. "
                "While your focus is admissions, ensure your answers are integrated and helpful even if the user mentions related course or financial topics."
            )
        if mode == "course":
            return (
                "AGENT EXPERTISE: COURSE ASSISTANT.\n"
                "You are the official DIU Course Agent. Your expertise is curricula, program structures, and academic roadmaps.\n"
                "Provide deep, exhaustive insights into programs and credits. "
                "Maintain your focus on academic content while ensuring a seamless, intelligent user experience across related categories."
            )
        if mode == "scholarship":
            return (
                "AGENT EXPERTISE: SCHOLARSHIP ASSISTANT.\n"
                "You are the official DIU Scholarship Agent. Your expertise is waivers, financial aid, and tuition optimization.\n"
                "Provide precise, multi-layered calculations and eligibility details. "
                "Focus on the financial architecture of the DIU journey while remaining helpful on the broader context of the university."
            )
        return (
            "AGENT ROLE: GENERAL FAQ ASSISTANT.\n"
            "You are the primary DIU Assistant. Your mission is to answer general university queries with absolute clarity and professional polish.\n"
            "Follow the global FORMATTING PROTOCOL strictly: ensure a point-by-point, highly organized, and visually cool response."
        )

    def _canvas_instruction(self) -> str:
        styles = [
            "Modern Professional (clean lines, data-first)",
            "Elite Dashboard (dark mode, vibrant accents)",
            "Functional Minimalist (typography-focused)",
            "Material Professional (clean surfaces, depth)"
        ]
        chosen_style = random.choice(styles)
        
        return (
            "CRITICAL OVERRIDE: You are now a senior frontend developer and Senior Full-Stack Web Architect and UI/UX Designer. "
            "Your goal is to generate a full-fledged, standalone, premium HTML/Tailwind application or landing page.\n\n"
            f"DESIGN PHILOSOPHY: Use a '{chosen_style}' aesthetic. Create a truly professional experience with a structured navbar, hero section, detailed content grids, and a footer.\n"
            "DIU BRAND SYSTEM:\n"
            "- Dark Mode Primary: #0b0f19\n"
            "- Brand Greens: #183b2d (900), #245f35 (800), #2f7a45 (700), #5fb171 (500)\n"
            "- Background: Use sophisticated subtle gradients (e.g., from #0b0f19 to #173124).\n"
            "- Typography: Use 'Outfit' for headings and 'Inter' for body text.\n\n"
            "MANDATORY: Use Tailwind CSS via <script src=\"https://cdn.tailwindcss.com\"></script>.\n"
            "COMPLEX STYLING: You MUST write custom CSS in a <style> block for premium animations, glassmorphism, hover effects, and unique layouts. "
            "Ensure the design feels fluid, with staggered reveal animations and smooth hover transitions for all interactive cards.\n"
            "MANDATORY: All text must be clearly legible with high contrast. Use plenty of whitespace and consistent padding.\n"
            "RETURN FORMAT: Return EXACTLY ONE ```html block. No conversational text.\n\n"
            
            "=== WEBSITE ARCHITECTURE ===\n"
            "- NAVBAR: Include a logo placeholder (DIU Assistant) and navigation links to the main content sections.\n"
            "- HERO SECTION: Start with a powerful, visually stunning hero section with a clear H1 and functional action controls.\n"
            "- CONTENT: Use the factual university data provided to build informative sections (e.g., 'Program Overview', 'Fee Tables', 'Scholarship Calculator').\n"
            "- TABLES: Format all data (fees, credits) into beautiful, searchable Tailwind tables.\n"
            "- FOOTER: Include a professional footer with university contact info placeholders.\n\n"

            "=== FUNCTIONALITY RULES ===\n"
            "- NO PLACEHOLDERS: Use ONLY factual data from the context.\n"
            "- NO DEAD BUTTONS: Every <button>, CTA, nav item, tab, chip, and card action MUST do something visible.\n"
            "- SINGLE-PAGE APP BEHAVIOR: Since this runs inside one canvas iframe, do not link to fake pages. Build a one-page mini-app with sections, tabs, filters, accordions, modals, calculators, search, sort, copy, or smooth-scroll anchors.\n"
            "- BUTTON CONTRACT: For each button, provide either an onclick handler, an event listener, a valid internal href target, or a form action that updates the page. If no real action exists, render it as plain text, not a button.\n"
            "- INTERACTIVITY: Include a <script> block that wires all controls after DOMContentLoaded. Active states must update visibly.\n"
            "- SMOOTHNESS: Use CSS transitions and Framer-like animations.\n"
            "- COMPLETENESS: Generate the full <html> document. NEVER truncate or stop mid-snippet."
        )

    def _should_include_canvas_instruction(self, user_question: str) -> bool:
        normalized = str(user_question or "").lower()
        if not normalized.strip():
            return False

        # Only trigger canvas if the user specifically asks for it via the UI button
        # or explicit visual keywords. This prevents hallucinated artifacts.
        signals = (
            "canvas force unlock",
            "generate an interactive visual version",
            "visual version", 
            "visualization",
            "visualizer",
            "generate canvas", 
            "show me visually",
            "interactive version",
            "build a calculator tool",
            "visual wizard",
            "website",
            "landing page",
            "full site",
            "dashboard",
            "portal",
            "app"
        )
        return any(signal in normalized for signal in signals)

    def _build_prompt(
        self,
        *,
        user_question: str,
        matches: list,
        language: str,
        chat_history: list[dict] | None = None,
        mode: str = "assistant",
    ) -> str:
        preferred_language = "Bangla" if language == "bn" else "English"
        agent_instruction = self._build_agent_instruction(mode)
        context_blocks: list[str] = []
        for index, match in enumerate(matches, start=1):
            excerpt = self._context_excerpt(match.chunk.text)
            source_url = getattr(match.chunk, "url", "") or getattr(match.chunk, "source", "")
            context_blocks.append(
                f"--- (Context {index}) ---\n"
                f"Title: {match.chunk.title}\n"
                f"URL: {source_url}\n"
                f"Excerpt: {excerpt}\n"
            )

        joined_context = "\n".join(context_blocks)
        is_canvas = self._should_include_canvas_instruction(user_question)
        canvas_rules = f"{self._canvas_instruction()}\n\n" if is_canvas else ""
        effective_agent_instruction = "SYSTEM: Canvas Artifact Generation Mode." if is_canvas else agent_instruction

        return (
            f"{effective_agent_instruction}\n\n"
            f"Preferred response language: {preferred_language}\n"
            f"User question: {user_question}\n\n"
            "Return only the answer body.\n"
            f"{canvas_rules}"
            f"Context Excerpts:\n{joined_context}\n"
        )

    def _build_freeform_prompt(
        self,
        *,
        user_question: str,
        language: str,
        chat_history: list[dict] | None = None,
        mode: str = "assistant",
    ) -> str:
        preferred_language = "Bangla" if language == "bn" else "English"
        agent_instruction = self._build_agent_instruction(mode)
        is_canvas = self._should_include_canvas_instruction(user_question)
        canvas_rules = f"{self._canvas_instruction()}\n\n" if is_canvas else ""
        effective_agent_instruction = "SYSTEM: Canvas Artifact Generation Mode." if is_canvas else agent_instruction

        return (
            f"{effective_agent_instruction}\n\n"
            f"Preferred response language: {preferred_language}\n"
            f"User question: {user_question}\n\n"
            f"{canvas_rules}"
        )

    def _generate(self, payload: dict) -> dict:
        errors: list[str] = []
        self.last_successful_model = ""
        key_list = self._ordered_api_keys()
        for model in dict.fromkeys(self.model_candidates):
            for key_index, api_key in key_list:
                try:
                    return self._generate_for_attempt(
                        payload,
                        model=model,
                        api_key=api_key,
                        key_index=key_index,
                    )
                except RuntimeError as exc:
                    errors.append(f"key {key_index} {model}: {exc}")

        self.last_error = " | ".join(errors)
        raise RuntimeError(self.last_error or "Gemini API request failed.")

    def _generate_transcription(self, payload: dict) -> dict:
        errors: list[str] = []
        self.last_successful_model = ""
        key_list = self._ordered_api_keys()
        for model in dict.fromkeys(self.transcribe_model_candidates):
            for key_index, api_key in key_list:
                try:
                    return self._generate_with_model(
                        payload,
                        model,
                        api_key,
                        timeout=self.transcribe_timeout,
                    )
                except RuntimeError as exc:
                    errors.append(f"key {key_index} {model}: {exc}")

        self.last_error = " | ".join(errors)
        raise RuntimeError(self.last_error or "Gemini transcription request failed.")

    def _generate_for_attempt(
        self,
        payload: dict,
        *,
        model: str,
        api_key: str,
        key_index: int,
    ) -> dict:
        errors: list[str] = []
        queue: list[tuple[str, dict]] = [("default", payload)]
        attempted: set[str] = set()
        delayed_retries: set[str] = set()

        while queue:
            label, candidate_payload = queue.pop(0)
            signature = json.dumps(candidate_payload, sort_keys=True)
            attempt_key = f"{key_index}:{model}:{label}:{signature}"
            if attempt_key in attempted:
                continue
            attempted.add(attempt_key)

            try:
                return self._generate_with_model(candidate_payload, model, api_key)
            except (RuntimeError, TimeoutError, OSError) as exc:
                error_text = str(exc)
                errors.append(f"{label}: {error_text}")
                retry_after = extract_retry_after_seconds(error_text)
                if (
                    retry_after is not None
                    and retry_after <= self.max_retry_after_seconds
                    and attempt_key not in delayed_retries
                ):
                    delayed_retries.add(attempt_key)
                    time.sleep(retry_after)
                    queue.insert(0, (label, candidate_payload))
                    continue
                queue.extend(self._retry_payloads(candidate_payload, error_text))

        raise RuntimeError(" | ".join(errors))

    def _retry_payloads(self, payload: dict, error_text: str) -> list[tuple[str, dict]]:
        lowered = error_text.lower()
        variants: list[tuple[str, dict]] = []

        if "thinkingconfig" in lowered or "thinking_config" in lowered:
            no_thinking_payload = json.loads(json.dumps(payload))
            no_thinking_payload.get("generationConfig", {}).pop("thinkingConfig", None)
            variants.append(("without thinkingConfig", no_thinking_payload))

        if "maxoutputtokens" in lowered or "max_output_tokens" in lowered or "max output tokens" in lowered:
            generation_config = payload.get("generationConfig") or {}
            current_limit = int(generation_config.get("maxOutputTokens") or 0)
            if current_limit > 32768:
                supported_limit_payload = json.loads(json.dumps(payload))
                supported_limit_payload.setdefault("generationConfig", {})["maxOutputTokens"] = 32768
                variants.append(("with supported output limit", supported_limit_payload))

        if (
            "google_search" in lowered
            or "google search" in lowered
            or "grounding" in lowered
            or "tool" in lowered
            or "429" in lowered
            or "resource_exhausted" in lowered
        ) and payload.get("tools"):
            no_search_payload = json.loads(json.dumps(payload))
            no_search_payload.pop("tools", None)
            variants.append(("without google_search", no_search_payload))

        return variants

    def _stream_generate(self, payload: dict, candidates: list[str] | None = None, api_keys: list[str] | None = None, timeout: int | None = None):
        errors: list[str] = []
        self.last_successful_model = ""
        model_list = candidates if candidates is not None else self.model_candidates
        key_list = (
            list(enumerate(api_keys, start=1))
            if api_keys is not None
            else self._ordered_api_keys()
        )
        for model in dict.fromkeys(model_list):
            for key_index, api_key in key_list:
                queue: list[tuple[str, dict]] = [("default", payload)]
                attempted: set[str] = set()
                delayed_retries: set[str] = set()

                while queue:
                    label, candidate_payload = queue.pop(0)
                    signature = json.dumps(candidate_payload, sort_keys=True)
                    attempt_key = f"{key_index}:{model}:{label}:{signature}"
                    if attempt_key in attempted:
                        continue
                    attempted.add(attempt_key)

                    try:
                        has_yielded = False
                        for chunk in self._stream_generate_with_model(
                            candidate_payload,
                            model=model,
                            api_key=api_key,
                            timeout=timeout,
                        ):
                            has_yielded = True
                            yield chunk
                        return
                    except (RuntimeError, TimeoutError, OSError) as exc:
                        error_text = str(exc)
                        if has_yielded:
                            # If we already yielded content, a retry would produce duplicates.
                            # We stop here and let the caller handle the partial response.
                            print(f"[Gemini] Stream failed mid-way on key {key_index}: {error_text}")
                            raise
                        
                        errors.append(f"key {key_index} {model} ({label}): {error_text}")
                        retry_after = extract_retry_after_seconds(error_text)
                        
                        if (
                            retry_after is not None
                            and retry_after <= self.max_retry_after_seconds
                            and attempt_key not in delayed_retries
                        ):
                            delayed_retries.add(attempt_key)
                            time.sleep(retry_after)
                            queue.insert(0, (label, candidate_payload))
                            continue
                        
                        variants = self._retry_payloads(candidate_payload, error_text)
                        if variants:
                            queue.extend(variants)
                        else:
                            # No more variants for this key/model, move to next key
                            break

        self.last_error = " | ".join(errors)
        raise RuntimeError(self.last_error or "Gemini API streaming request failed.")

    def _ordered_api_keys(self) -> list[tuple[int, str]]:
        if not self.api_keys:
            return []
        indexed_keys = list(enumerate(self.api_keys, start=1))
        offset = self._next_key_offset % len(indexed_keys)
        self._next_key_offset = (self._next_key_offset + 1) % len(indexed_keys)
        return [*indexed_keys[offset:], *indexed_keys[:offset]]

    def _stream_generate_with_model(
        self,
        payload: dict,
        model: str,
        api_key: str,
        timeout: int | None = None,
    ):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                self.last_error = ""
                self.last_successful_model = model
                saw_truncation = False
                
                # Parse SSE stream
                for line in response:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            chunk_data = json.loads(data_str)
                            text = self._extract_text(chunk_data)
                            if text:
                                yield text
                            if self._payload_truncated(chunk_data):
                                saw_truncation = True
                            # Optional: remember grounding sources from chunks
                            self._remember_grounding_sources(chunk_data)
                        except json.JSONDecodeError:
                            continue
                if saw_truncation:
                    raise RuntimeError("Gemini stream hit the output limit before the answer completed.")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code} {details}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"connection error: {exc}") from exc

    def _generate_with_model(
        self,
        payload: dict,
        model: str,
        api_key: str | None = None,
        *,
        timeout: int | None = None,
    ) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key or self.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                self.last_error = ""
                self.last_successful_model = model
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code} {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"connection error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("connection error: timed out") from exc
        except OSError as exc:
            raise RuntimeError(f"connection error: {exc}") from exc

    def _add_google_search_tool(self, payload: dict, *, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = self.enable_google_search
        if enabled:
            payload["tools"] = [{"google_search": {}}]

    def _bounded_max_tokens(self, requested_limit: int) -> int:
        return max(512, min(self.max_output_tokens, int(requested_limit)))

    def _response_token_budget(
        self,
        *,
        mode: str = "assistant",
        is_canvas: bool = False,
        has_documents: bool = False,
    ) -> int:
        if is_canvas:
            return self._bounded_max_tokens(self.canvas_max_output_tokens)
        if has_documents:
            return self._bounded_max_tokens(self.document_max_output_tokens)
        if mode != "assistant":
            return self._bounded_max_tokens(max(self.standard_max_output_tokens, 8192))
        return self._bounded_max_tokens(self.standard_max_output_tokens)

    def _remember_grounding_sources(self, payload: dict) -> None:
        urls: list[str] = []
        titles: list[str] = []
        seen: set[str] = set()

        for candidate in payload.get("candidates", []):
            metadata = candidate.get("groundingMetadata") or candidate.get("grounding_metadata") or {}
            for chunk in metadata.get("groundingChunks", []) or metadata.get("grounding_chunks", []):
                web = chunk.get("web") or {}
                uri = web.get("uri")
                title = web.get("title") or uri
                if not uri or uri in seen:
                    continue
                seen.add(uri)
                urls.append(uri)
                titles.append(title)

        self.last_grounding_sources = urls
        self.last_grounding_titles = titles

    def _env_flag(self, name: str, *, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() not in {"0", "false", "no", "off"}


    def _format_history(self, chat_history: list[dict] | None) -> str:
        if not chat_history:
            return "(none)"
        lines: list[str] = []
        for index, message in enumerate(chat_history, start=1):
            role = message.get("role", "user")
            mode = str(message.get("mode", "")).strip()
            content = str(message.get("content", "")).strip()
            if content:
                label = f"{role} [{mode}]" if mode else str(role)
                lines.append(f"{index}. {label}: {content}")
        return "\n".join(lines) if lines else "(none)"

    def _context_excerpt(self, text: str) -> str:
        excerpt = re.sub(r"\s+", " ", str(text or "")).strip()
        if self.context_chars <= 0:
            return excerpt
        return excerpt[: self.context_chars]

    def _extract_text(self, payload: dict) -> str:
        parts: list[str] = []
        for candidate in payload.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                # Skip thinking/reasoning parts — they are internal model thoughts
                if part.get("thought"):
                    continue
                text = part.get("text")
                if text:
                    parts.append(text)
        return "".join(parts)

    def _payload_truncated(self, payload: dict) -> bool:
        truncated_reasons = {"MAX_TOKENS", "MAX_OUTPUT_TOKENS"}
        for candidate in payload.get("candidates", []):
            reason = str(candidate.get("finishReason") or candidate.get("finish_reason") or "").strip().upper()
            if reason in truncated_reasons:
                return True
        return False

    def _clean_text(self, text: str) -> str:
        # Preserve model wording; callers sanitize provider identity separately.
        return str(text or "").strip()

    def _clean_transcript(self, text: str) -> str:
        text = re.sub(r"^\s*(transcript|transcription)\s*:\s*", "", text.strip(), flags=re.IGNORECASE)
        text = text.strip().strip('"').strip("'").strip()
        text = re.sub(r"\s+", " ", text).strip()

        lowered = text.lower()
        non_transcript_markers = (
            "[no_speech]",
            "cannot fulfill this request",
            "audio provided does not contain any spoken words",
            "does not contain any spoken words",
            "does not contain spoken words",
            "no spoken words",
            "no speech detected",
            "no intelligible spoken words",
            "no intelligible speech",
            "no audible speech",
            "speech is not detectable",
            "could not detect any speech",
            "couldn't detect any speech",
            "unable to transcribe",
            "unable to detect speech",
            "inaudible",
            "silent audio",
        )
        if any(marker in lowered for marker in non_transcript_markers):
            return ""

        return text

    def _sanitize_identity_leaks(self, text: str) -> str:
        replacements = (
            (
                r"^\s*(?:i am|i'm)\s+(?:google(?:'s)?\s+)?gemini(?:\s+\w+)*[,.:\-\s]*",
                "I’m the DIU Assistant. ",
            ),
            (
                r"^\s*(?:i am|i'm)\s+(?:an?\s+)?(?:ai language model|ai assistant|ai model|language model|large language model|ai)[,.:\-\s]*",
                "I’m the DIU Assistant. ",
            ),
            (
                r"^\s*as\s+(?:google(?:'s)?\s+)?gemini(?:\s+\w+)*[,:]?\s*",
                "",
            ),
            (
                r"^\s*as\s+(?:an?\s+)?(?:ai language model|ai assistant|ai model|language model|large language model|ai)[,:]?\s*",
                "",
            ),
        )
        cleaned = text.strip()
        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"^\s*(?:i am|i'm)\s+(?:google(?:'s)?\s+)?gemini(?:\s+\w+)*[,.:\-\s]*",
            "I’m the DIU Assistant. ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:Google\s+Gemini|Gemini)\b(?=\s+(?:assistant|model|api)\b)",
            "the DIU Assistant",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:powered|built|run)\s+by\s+(?:Google\s+Gemini|Gemini)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\bmy capabilities\s+(?:are\s+)?(?:powered|built|run)\s+by\s+(?:Google\s+Gemini|Gemini)\b[,.:\-\s]*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:the\s+)?google(?:'s)?\s+(?:ai language model|ai assistant|ai model|language model|large language model)\b[,.:\-\s]*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[^\S\n]+", " ", cleaned)
        cleaned = re.sub(
            r"\b(?:as\s+)?an?\s+(?:AI language model|AI assistant|AI model|language model|large language model|AI)\b",
            "as the DIU Assistant",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(I’m the DIU Assistant\.\s*){2,}", "I’m the DIU Assistant. ", cleaned)
        return cleaned.strip()
