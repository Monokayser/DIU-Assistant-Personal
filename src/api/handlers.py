from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.apps.canvas.services.artifacts import (
    build_canvas_reply_text,
    create_canvas_artifacts,
    should_create_canvas_artifacts,
)
from src.apps.documents.rag.pipeline import RAGPipeline, SupabaseConfigError, parse_uploaded_file
from src.api.errors import extract_retry_after_seconds, format_backend_error, is_daily_free_tier_quota
from src.core.observability import log_event, normalize_question, truncate_text

# These will be initialized by the server or passed in
AI_CLIENT = None
WEBSITE_BOT = None
DOCUMENT_PIPELINES: dict[str, RAGPipeline] = {}
UPLOADED_FILE_CONTEXTS: dict[str, dict[str, dict[str, Any]]] = {}

UPLOADED_CONTEXT_DIR = Path("tmp/uploaded_contexts")
CANVAS_ARTIFACTS_DIR = Path("tmp/canvas_artifacts")
CANVAS_SOURCE_CHAR_LIMIT = 24000

def initialize_handlers(ai_client, website_bot, root_path: Path):
    global AI_CLIENT, WEBSITE_BOT, UPLOADED_CONTEXT_DIR, CANVAS_ARTIFACTS_DIR
    AI_CLIENT = ai_client
    WEBSITE_BOT = website_bot
    UPLOADED_CONTEXT_DIR = root_path / "tmp" / "uploaded_contexts"
    CANVAS_ARTIFACTS_DIR = root_path / "tmp" / "canvas_artifacts"

def model_is_configured() -> bool:
    return bool(getattr(AI_CLIENT, "is_configured", False))

def to_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default

def decode_direct_file_payloads(files: list[Any] | None) -> list[dict[str, Any]]:
    decoded: list[dict[str, Any]] = []
    for item in files or []:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "upload").strip() or "upload"
        content_base64 = str(
            item.get("content_base64")
            or item.get("fileData")
            or item.get("file_data")
            or ""
        ).strip()
        if not content_base64:
            continue
        try:
            file_bytes = base64.b64decode(content_base64)
        except Exception:
            continue
        decoded.append(
            {
                "filename": filename,
                "mime_type": str(item.get("mime_type") or item.get("mimeType") or "").strip(),
                "file_bytes": file_bytes,
            }
        )
    return decoded

def detect_language(text: str) -> str:
    return "bn" if any("\u0980" <= char <= "\u09ff" for char in text) else "en"

def normalize_attached_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).strip()

def uploaded_context_path(session_id: str) -> Path:
    safe_session = re.sub(r"[^a-zA-Z0-9._-]+", "_", session_id.strip() or "default").strip("._") or "default"
    return UPLOADED_CONTEXT_DIR / f"{safe_session}.json"

def load_persisted_uploaded_context(session_id: str) -> dict[str, dict[str, Any]]:
    path = uploaded_context_path(session_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    cleaned: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        normalized_key = normalize_attached_name(key)
        if not normalized_key:
            continue
        cleaned[normalized_key] = {
            "title": str(value.get("title") or "Uploaded document").strip() or "Uploaded document",
            "source": str(value.get("source") or "").strip(),
            "url": str(value.get("url") or "").strip(),
            "content": str(value.get("content") or "").strip(),
            "mime_type": str(value.get("mime_type") or "").strip(),
        }
    return cleaned

def load_session_uploaded_context(session_id: str) -> dict[str, dict[str, Any]]:
    return {
        **load_persisted_uploaded_context(session_id),
        **UPLOADED_FILE_CONTEXTS.get(session_id, {}),
    }

def persist_uploaded_context(session_id: str, normalized_name: str, payload: dict[str, Any]) -> None:
    path = uploaded_context_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_persisted_uploaded_context(session_id)
    current[normalized_name] = payload
    path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")

def remember_uploaded_context(
    session_id: str,
    filename: str,
    *,
    text: str,
    mime_type: str | None = None,
) -> None:
    clean_session_id = session_id.strip() or "default"
    normalized_name = normalize_attached_name(filename)
    if not clean_session_id or not normalized_name or not text.strip():
        return
    payload = {
        "title": Path(filename).stem.replace("_", " ").replace("-", " ").title(),
        "source": filename,
        "url": filename,
        "content": text,
        "mime_type": mime_type or "",
    }
    UPLOADED_FILE_CONTEXTS.setdefault(clean_session_id, {})[normalized_name] = payload
    persist_uploaded_context(clean_session_id, normalized_name, payload)

def get_uploaded_context_for_session(
    session_id: str,
    attached_files: list[str] | None,
) -> list[dict[str, Any]]:
    clean_session_id = session_id.strip() or "default"
    session_context = load_session_uploaded_context(clean_session_id)
    if session_context:
        UPLOADED_FILE_CONTEXTS[clean_session_id] = session_context
    targets = {
        normalize_attached_name(name)
        for name in (attached_files or [])
        if normalize_attached_name(name)
    }
    if not targets:
        return []
    results: list[dict[str, Any]] = []
    for target in targets:
        item = session_context.get(target)
        if item:
            results.append(item)
    return results

def list_uploaded_context_for_session(session_id: str) -> list[dict[str, Any]]:
    clean_session_id = session_id.strip() or "default"
    session_context = load_session_uploaded_context(clean_session_id)
    if session_context:
        UPLOADED_FILE_CONTEXTS[clean_session_id] = session_context
    return list(session_context.values())

def build_context_matches(context: list[Any]) -> list[SimpleNamespace]:
    matches: list[SimpleNamespace] = []
    for index, item in enumerate(context, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("content", "")).strip()
        if not text:
            continue
        title = str(item.get("title") or item.get("source") or f"Document {index}").strip()
        url = str(item.get("url") or item.get("source") or "").strip()
        chunk = SimpleNamespace(
            title=title,
            url=url,
            source=url or title,
            text=text,
        )
        matches.append(SimpleNamespace(chunk=chunk, score=1.0))
    return matches

def filter_context_for_attached_files(
    context: list[Any],
    attached_files: list[str] | None,
) -> list[Any]:
    normalized_targets = {
        normalize_attached_name(name)
        for name in (attached_files or [])
        if normalize_attached_name(name)
    }
    if not normalized_targets:
        return []

    filtered: list[Any] = []
    for item in context:
        if not isinstance(item, dict):
            continue
        source_parts = [
            str(item.get("source") or "").strip(),
            str(item.get("title") or "").strip(),
            str(item.get("url") or "").strip(),
        ]
        haystack = normalize_attached_name(" ".join(source_parts))
        if haystack and any(target in haystack for target in normalized_targets):
            filtered.append(item)
    return filtered

def resolve_uploaded_context_matches(
    context: list[Any],
    *,
    session_id: str | None = None,
    attached_files: list[str] | None = None,
) -> tuple[list[SimpleNamespace], bool]:
    has_attachment_filter = any(str(name).strip() for name in (attached_files or []))
    selected_context = (
        filter_context_for_attached_files(context, attached_files)
        if has_attachment_filter
        else context
    )
    matches = build_context_matches(selected_context)
    if matches or not has_attachment_filter or not session_id:
        return matches, has_attachment_filter

    remembered_context = get_uploaded_context_for_session(session_id, attached_files)
    matches = build_context_matches(remembered_context)
    if matches:
        return matches, has_attachment_filter

    return build_context_matches(list_uploaded_context_for_session(session_id)), has_attachment_filter

def get_document_pipeline(session_id: str) -> RAGPipeline:
    clean_session_id = session_id.strip() or "default"
    if clean_session_id not in DOCUMENT_PIPELINES:
        DOCUMENT_PIPELINES[clean_session_id] = RAGPipeline(
            gemini_client=AI_CLIENT,
            session_id=clean_session_id,
        )
    return DOCUMENT_PIPELINES[clean_session_id]

def ingest_upload(
    session_id: str,
    filename: str,
    file_bytes: bytes,
    *,
    mime_type: str | None = None,
    return_text: bool = False,
) -> dict[str, Any]:
    mime_type = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    extracted_with = "parser"
    try:
        text = parse_uploaded_file(file_bytes, filename)
    except Exception as parser_error:
        if not model_is_configured():
            raise parser_error
        text = AI_CLIENT.extract_upload_text(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
        )
        extracted_with = "gemini"

    if not text.strip() and model_is_configured():
        text = AI_CLIENT.extract_upload_text(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
        )
        extracted_with = "gemini"

    if not text.strip():
        return {
            "filename": filename,
            "chunks": 0,
            "stored": False,
            "mime_type": mime_type,
            "extracted_with": extracted_with,
            "text": "" if return_text else None,
        }

    stored = False
    chunks = 0
    try:
        pipeline = get_document_pipeline(session_id)
        chunks = pipeline.ingest_text(text, filename)
        stored = chunks > 0
    except SupabaseConfigError:
        pass
    except RuntimeError as exc:
        if "Supabase" not in str(exc):
            raise

    payload: dict[str, Any] = {
        "filename": filename,
        "chunks": chunks,
        "stored": stored,
        "mime_type": mime_type,
        "extracted_with": extracted_with,
    }
    remember_uploaded_context(
        session_id,
        filename,
        text=text,
        mime_type=mime_type,
    )
    if return_text or not stored:
        payload["text"] = text
    return payload

def answer_from_university_knowledge(
    message: str,
    history: list[dict[str, Any]],
    session_id: str,
    attached_files: list[str],
    mode: str,
    *,
    allow_local_grounding: bool = False,
) -> dict[str, Any]:
    effective_history = [] if mode == "assistant" else history
    response = WEBSITE_BOT.answer(
        message,
        chat_history=effective_history,
        allow_local_grounding=allow_local_grounding,
        mode=mode,
    )

    sources = []
    for title, url in zip(response.source_titles, response.source_urls):
        if not url:
            continue
        clean_url = str(url).strip()
        sources.append(
            {
                "title": title or "Source",
                "url": clean_url if clean_url.startswith(("http://", "https://")) else None,
                "source": None if clean_url.startswith(("http://", "https://")) else clean_url,
            }
        )

    artifacts = []
    if mode != "assistant" and should_create_canvas_artifacts(message, response.answer):
        artifacts = create_canvas_artifacts(
            CANVAS_ARTIFACTS_DIR,
            session_id=session_id,
            question=message,
            answer=response.answer,
            sources=sources[:3],
        )

    return {
        "answer": build_canvas_reply_text(message, response.answer) if artifacts else response.answer,
        "sources": sources[:3],
        "used_model": bool(response.used_gemini),
        "found_match": bool(response.found_match),
        "artifacts": artifacts,
    }

def build_canvas_website_prompt(source_content: str, *, title: str = "") -> str:
    clean_content = re.sub(r"\s+\n", "\n", str(source_content or "")).strip()
    clean_title = str(title or "").strip()
    title_line = f"Website title/topic: {clean_title}\n\n" if clean_title else ""
    return (
        "Create a complete standalone website from the following content. "
        "Return only one full HTML document with responsive layout, polished visual design, "
        "semantic sections, accessible contrast, and no document-workspace wrapper. "
        "Use the factual content below; do not invent university facts. "
        "If tables are needed, ensure every row has a consistent column count. "
        "This canvas is a single-page mini-app, so every button, CTA, nav link, card action, tab, chip, and form control must be functional. "
        "Do not create decorative or dead buttons. Use internal anchors, smooth scrolling, tabs, accordions, filters, searchable/sortable tables, modals, calculators, copy actions, or visible active-state changes. "
        "Include JavaScript in a <script> block that wires all interactive controls after DOMContentLoaded. "
        "[canvas force unlock]\n\n"
        f"{title_line}"
        f"{clean_content[:CANVAS_SOURCE_CHAR_LIMIT]}"
    )

def create_canvas_website_from_content(
    *,
    source_content: str,
    session_id: str,
    mode: str,
    title: str = "",
    allow_local_grounding: bool = True,
) -> dict[str, Any]:
    clean_content = str(source_content or "").strip()
    if not clean_content:
        return {
            "error": "No source content was provided for canvas generation.",
            "answer": "No source content was provided for canvas generation.",
            "sources": [],
            "used_model": False,
            "found_match": False,
            "artifacts": [],
        }

    prompt = build_canvas_website_prompt(clean_content, title=title)
    response = WEBSITE_BOT.answer(
        prompt,
        chat_history=[],
        allow_local_grounding=allow_local_grounding,
        mode=mode,
    )

    sources = []
    for source_title, url in zip(response.source_titles, response.source_urls):
        if not url:
            continue
        clean_url = str(url).strip()
        sources.append(
            {
                "title": source_title or "Source",
                "url": clean_url if clean_url.startswith(("http://", "https://")) else None,
                "source": None if clean_url.startswith(("http://", "https://")) else clean_url,
            }
        )

    artifacts = create_canvas_artifacts(
        CANVAS_ARTIFACTS_DIR,
        session_id=session_id,
        question=prompt,
        answer=response.answer,
        sources=sources[:3],
        require_model_html=True,
    )
    if not artifacts:
        message = (
            "The model did not return a valid standalone HTML website. "
            "Please retry canvas generation."
        )
        return {
            "error": message,
            "answer": message,
            "sources": sources[:3],
            "used_model": bool(response.used_gemini),
            "found_match": bool(response.found_match),
            "artifacts": [],
        }

    return {
        "answer": "Here is your website canvas. Open the canvas to explore it.",
        "sources": sources[:3],
        "used_model": bool(response.used_gemini),
        "found_match": bool(response.found_match),
        "artifacts": artifacts,
    }

class StreamingStripper:
    def __init__(self, is_canvas_request: bool = False):
        self.full_content = ""
        self.stop_yielding = False
        self.is_canvas_request = is_canvas_request
        self.chunk_counter = 0

    def process(self, chunk: str) -> tuple[str | None, dict | None]:
        if not self.is_canvas_request:
            return chunk, None

        if self.stop_yielding:
            self.chunk_counter += 1
            if self.chunk_counter % 40 == 0:
                return None, {"status": "generating_artifact", "heartbeat": True}
            return None, None
        
        old_len = len(self.full_content)
        self.full_content += chunk
        
        marker_match = re.search(
            r"```|<!doctype|<html|<(?:body|main|section|article|div|header|nav|aside|form|label|input|select|option|button|canvas|svg|style|script|p)\b|\[canvas force unlock\]",
            self.full_content,
            re.IGNORECASE,
        )
        found_idx = marker_match.start() if marker_match else -1
        
        if found_idx != -1:
            self.stop_yielding = True
            offset = found_idx - old_len
            pre_chunk = chunk[:offset] if offset > 0 else None
            return pre_chunk, {"status": "generating_artifact"}

        return chunk, None

def stream_answer_from_university_knowledge(
    message: str,
    history: list[dict[str, Any]],
    session_id: str,
    attached_files: list[str],
    mode: str,
    *,
    allow_local_grounding: bool = False,
):
    effective_history = [] if mode == "assistant" else history
    is_canvas = "[canvas force unlock]" in message.lower()
    stripper = StreamingStripper(is_canvas_request=is_canvas)
    final_answer = ""
    
    for chunk in WEBSITE_BOT.stream_answer(
        message,
        chat_history=effective_history,
        allow_local_grounding=allow_local_grounding,
        mode=mode,
    ):
        if chunk.get("done"):
            final_answer = chunk.get("answer", "")
            sources = chunk.get("sources", [])
            artifacts = []
            if mode != "assistant" and should_create_canvas_artifacts(message, final_answer):
                artifacts = create_canvas_artifacts(
                    CANVAS_ARTIFACTS_DIR,
                    session_id=session_id,
                    question=message,
                    answer=final_answer,
                    sources=sources[:3],
                )
            chunk["artifacts"] = artifacts
            chunk["answer"] = build_canvas_reply_text(message, final_answer) if artifacts else final_answer
            yield chunk
            break

        text_chunk = chunk.get("chunk", "")
        final_answer += text_chunk
        clean_chunk, status = stripper.process(text_chunk)
        
        if status:
            yield status
            
        if clean_chunk is not None:
            chunk["chunk"] = clean_chunk
            yield chunk
        elif stripper.stop_yielding:
            continue
        else:
            yield chunk

def stream_answer_from_direct_uploads(
    message: str,
    history: list[dict[str, Any]],
    uploads: list[dict[str, Any]],
    *,
    session_id: str = "default",
    mode: str = "assistant",
):
    if not model_is_configured():
        raise RuntimeError("Gemini API key is not configured.")

    assistant_mode = mode == "assistant"
    effective_history = [] if assistant_mode else history
    
    stream = AI_CLIENT.stream_answer_with_uploads(
        user_question=message,
        uploads=uploads,
        language=detect_language(message),
        chat_history=effective_history,
        assistant_mode=assistant_mode,
        force_fast=True,
    )
    
    full_answer = ""
    is_canvas = "[canvas force unlock]" in message.lower()
    stripper = StreamingStripper(is_canvas_request=is_canvas)
    for chunk in stream:
        if isinstance(chunk, dict) and "status" in chunk:
            yield chunk
            continue
            
        text_chunk = chunk.get("chunk", "") if isinstance(chunk, dict) else str(chunk)
        full_answer += text_chunk
        
        clean_chunk, status = stripper.process(text_chunk)
        if status:
            yield status
            
        if clean_chunk is not None:
            yield {"chunk": clean_chunk}
        elif stripper.stop_yielding:
            continue
        else:
            yield {"chunk": text_chunk}
        
    sources = [
        {
            "title": str(upload.get("filename") or "Uploaded file"),
            "source": str(upload.get("filename") or "Uploaded file"),
            "url": None,
        }
        for upload in uploads
    ]
    
    artifacts = []
    if not assistant_mode and (
        should_create_canvas_artifacts(message, full_answer)
        or bool(uploads)
    ):
        artifacts = create_canvas_artifacts(
            CANVAS_ARTIFACTS_DIR,
            session_id=session_id,
            question=message,
            answer=full_answer,
            sources=sources[:3],
        )
        
    yield {
        "done": True,
        "answer": build_canvas_reply_text(message, full_answer) if artifacts else full_answer,
        "sources": sources[:3],
        "used_model": True,
        "found_match": True,
        "artifacts": artifacts,
    }

def answer_from_direct_uploads(
    message: str,
    history: list[dict[str, Any]],
    uploads: list[dict[str, Any]],
    *,
    session_id: str = "default",
    mode: str = "assistant",
) -> dict[str, Any]:
    final_payload: dict[str, Any] | None = None
    accumulated = ""
    for chunk in stream_answer_from_direct_uploads(
        message,
        history,
        uploads,
        session_id=session_id,
        mode=mode,
    ):
        if chunk.get("done"):
            final_payload = chunk
            break
        accumulated += str(chunk.get("chunk") or "")

    if final_payload:
        return final_payload

    return {
        "answer": accumulated.strip() or "The uploaded file could not be analyzed right now.",
        "sources": [],
        "used_model": bool(accumulated.strip()),
        "found_match": bool(accumulated.strip()),
        "artifacts": [],
    }

def answer_from_uploaded_context(
    message: str,
    history: list[dict[str, Any]],
    context: list[dict[str, Any]],
    *,
    session_id: str = "default",
    attached_files: list[str] | None = None,
    mode: str = "assistant",
) -> dict[str, Any]:
    matches, _ = resolve_uploaded_context_matches(
        context,
        session_id=session_id,
        attached_files=attached_files,
    )
    if not matches:
        return {
            "answer": unreadable_upload_answer(detect_language(message)),
            "sources": [],
            "used_model": False,
            "found_match": False,
            "artifacts": [],
            "used_documents": True,
        }

    try:
        answer = AI_CLIENT.answer_from_context(
            user_question=message,
            matches=matches,
            language=detect_language(message),
            chat_history=history,
            mode=mode,
            enable_search=False,
        )
    except Exception as exc:
        return {"error": format_backend_error(exc), "answer": format_backend_error(exc), "sources": []}

    sources = [
        {
            "title": match.chunk.title,
            "source": match.chunk.source,
            "url": match.chunk.url if str(match.chunk.url).startswith(("http://", "https://")) else None,
        }
        for match in matches[:3]
    ]
    return {
        "answer": answer,
        "sources": sources,
        "used_model": True,
        "found_match": True,
        "artifacts": [],
        "used_documents": True,
    }

def is_uploaded_document_request(message: str) -> bool:
    normalized = " ".join(str(message or "").lower().split())
    return bool(
        normalized and re.search(
            r"\b(uploaded?|attached|attachments?|documents?|files?|pdf|summari[sz]e|summary|summaries)\b",
            normalized,
        )
    )

def unreadable_upload_answer(language: str) -> str:
    if language == "bn":
        return "আপলোড করা file পেয়েছি, কিন্তু এর readable text এখনও পাওয়া যায়নি। PDF বা document টি আবার upload করুন, অথবা text-select করে প্রশ্ন করুন।"
    return "I found the uploaded file, but I do not have readable text from it yet. Please upload the PDF or document again so I can extract and summarize its contents."

def with_model_metadata(payload: dict[str, Any], started_at: float) -> dict[str, Any]:
    enriched = dict(payload)
    enriched.update(
        {
            "provider": "gemini",
            "model": getattr(AI_CLIENT, "last_successful_model", "") or AI_CLIENT.model,
            "models": AI_CLIENT.model_candidates,
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        }
    )
    return enriched
