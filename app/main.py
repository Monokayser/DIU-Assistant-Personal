from __future__ import annotations

import os
import sys
import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Fix python path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.errors import format_backend_error
from src.core.config import load_local_env
from src.core.gemini import GeminiGroundedResponder
from src.core.knowledge import DIUCampusChatbot
from src.api.server import start_server
import src.api.handlers as handlers

_HANDLER_GET_DOCUMENT_PIPELINE = handlers.get_document_pipeline
_HANDLER_ANSWER_FROM_UNIVERSITY_KNOWLEDGE = handlers.answer_from_university_knowledge
_HANDLER_ANSWER_FROM_UPLOADED_CONTEXT = handlers.answer_from_uploaded_context
_HANDLER_ANSWER_FROM_DIRECT_UPLOADS = handlers.answer_from_direct_uploads

AI_CLIENT = None
WEBSITE_BOT = None
CANVAS_ARTIFACTS_DIR = ROOT / "tmp" / "canvas_artifacts"


def get_server_address() -> tuple[str, int]:
    host = str(os.getenv("API_HOST", "127.0.0.1")).strip() or "127.0.0.1"
    raw_port = str(os.getenv("API_PORT") or os.getenv("PORT") or "8765").strip() or "8765"
    try:
        port = int(raw_port)
    except ValueError:
        port = 8765
    return host, port


def format_server_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"", "0.0.0.0", "::"} else host
    return f"http://{display_host}:{port}"


def _sync_handler_state() -> None:
    handlers.AI_CLIENT = AI_CLIENT
    handlers.WEBSITE_BOT = WEBSITE_BOT
    handlers.CANVAS_ARTIFACTS_DIR = CANVAS_ARTIFACTS_DIR


def _sanitize_upload_name(value: str) -> str:
    cleaned = Path(str(value or "").strip() or "upload").name.strip()
    return cleaned or "upload"


def _call_with_synced_handlers(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    _sync_handler_state()
    original_get_document_pipeline = handlers.get_document_pipeline
    try:
        handlers.get_document_pipeline = get_document_pipeline
        return callback(*args, **kwargs)
    finally:
        handlers.get_document_pipeline = original_get_document_pipeline


def get_document_pipeline(session_id: str):
    _sync_handler_state()
    return _HANDLER_GET_DOCUMENT_PIPELINE(session_id)


def handle_upload(payload: dict[str, Any]) -> dict[str, Any]:
    _sync_handler_state()
    session_id = str(payload.get("session_id") or payload.get("sessionId") or "default").strip() or "default"
    wants_text = handlers.to_bool(payload.get("return_text"), default=False)
    files = payload.get("files")

    if isinstance(files, list):
        results = []
        for item in files:
            if not isinstance(item, dict):
                continue
            file_data_b64 = str(
                item.get("content_base64")
                or item.get("fileData")
                or item.get("file_data")
                or ""
            ).strip()
            if not file_data_b64:
                continue
            results.append(
                    handlers.ingest_upload(
                        session_id,
                        _sanitize_upload_name(str(item.get("filename") or "upload")),
                        base64.b64decode(file_data_b64),
                        mime_type=item.get("mimeType") or item.get("mime_type"),
                        return_text=wants_text,
                    )
            )
        return {"ok": True, "files": results}

    file_data_b64 = str(
        payload.get("content_base64")
        or payload.get("fileData")
        or payload.get("file_data")
        or ""
    ).strip()
    if not file_data_b64:
        raise ValueError("No file data provided")

    result = handlers.ingest_upload(
        session_id,
        _sanitize_upload_name(str(payload.get("filename") or "upload")),
        base64.b64decode(file_data_b64),
        mime_type=payload.get("mimeType") or payload.get("mime_type"),
        return_text=wants_text,
    )
    return {"ok": True, "file": result}


def answer_from_document_rag(
    message: str,
    history: list[dict[str, Any]],
    context: list[dict[str, Any]],
    session_id: str,
    *,
    attached_files: list[str] | None = None,
    mode: str = "assistant",
) -> dict[str, Any]:
    return _call_with_synced_handlers(
        _HANDLER_ANSWER_FROM_UPLOADED_CONTEXT,
        message,
        history,
        context,
        session_id=session_id,
        attached_files=attached_files,
        mode=mode,
    )


def answer_from_uploaded_context(
    message: str,
    history: list[dict[str, Any]],
    context: list[dict[str, Any]],
    *,
    session_id: str = "default",
    attached_files: list[str] | None = None,
    mode: str = "assistant",
) -> dict[str, Any]:
    return _call_with_synced_handlers(
        _HANDLER_ANSWER_FROM_UPLOADED_CONTEXT,
        message,
        history,
        context,
        session_id=session_id,
        attached_files=attached_files,
        mode=mode,
    )


def answer_from_direct_uploads(
    message: str,
    history: list[dict[str, Any]],
    uploads: list[dict[str, Any]],
    *,
    session_id: str = "default",
    mode: str = "assistant",
) -> dict[str, Any]:
    _sync_handler_state()

    if getattr(AI_CLIENT, "is_configured", False) and hasattr(AI_CLIENT, "answer_with_uploads"):
        assistant_mode = mode == "assistant"
        effective_history = [] if assistant_mode else history
        answer = AI_CLIENT.answer_with_uploads(
            user_question=message,
            uploads=uploads,
            language=handlers.detect_language(message),
            chat_history=effective_history,
            assistant_mode=assistant_mode,
        )
        sources = [
            {
                "title": str(upload.get("filename") or "Uploaded file"),
                "source": str(upload.get("filename") or "Uploaded file"),
                "url": None,
            }
            for upload in uploads
        ]
        artifacts = []
        if not assistant_mode and (handlers.should_create_canvas_artifacts(message, answer) or bool(uploads)):
            artifacts = handlers.create_canvas_artifacts(
                CANVAS_ARTIFACTS_DIR,
                session_id=session_id,
                question=message,
                answer=answer,
                sources=sources[:3],
            )
        return {
            "answer": handlers.build_canvas_reply_text(message, answer) if artifacts else answer,
            "sources": sources[:3],
            "used_model": True,
            "found_match": True,
            "artifacts": artifacts,
        }

    return _call_with_synced_handlers(
        _HANDLER_ANSWER_FROM_DIRECT_UPLOADS,
        message,
        history,
        uploads,
        session_id=session_id,
        mode=mode,
    )


def answer_from_university_knowledge(
    message: str,
    history: list[dict[str, Any]],
    session_id: str,
    attached_files: list[str],
    mode: str,
    *,
    allow_local_grounding: bool = False,
) -> dict[str, Any]:
    return _call_with_synced_handlers(
        _HANDLER_ANSWER_FROM_UNIVERSITY_KNOWLEDGE,
        message,
        history,
        session_id,
        attached_files,
        mode,
        allow_local_grounding=allow_local_grounding,
    )


def main() -> None:
    global AI_CLIENT, WEBSITE_BOT

    # 1. Load configuration
    load_local_env(ROOT / ".env")

    # 2. Initialize Core components
    AI_CLIENT = GeminiGroundedResponder()
    SITE_INDEX_PATH = ROOT / "data" / "processed" / "daffodil_site_index.json"
    WEBSITE_BOT = DIUCampusChatbot(
        SITE_INDEX_PATH,
        gemini_client=AI_CLIENT,
        auto_sync=False,
    )

    # 3. Initialize Handlers with shared state
    handlers.initialize_handlers(AI_CLIENT, WEBSITE_BOT, ROOT)

    # 4. Determine server address
    host, port = get_server_address()

    # 5. Start the server
    start_server(host, port)

if __name__ == "__main__":
    main()
