from __future__ import annotations

import base64
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.core.config import get_allowed_origin_patterns, resolve_allowed_origin
from src.apps.canvas.services.artifacts import guess_artifact_mime_type, resolve_artifact_path
from src.api.errors import format_upload_error

import src.api.handlers as handlers

class ChatHandler(BaseHTTPRequestHandler):
    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else {}

    def _send_security_headers(self) -> None:
        origin = self.headers.get("Origin")
        allowed_origins = get_allowed_origin_patterns()
        allowed_origin = resolve_allowed_origin(origin, allowed_origins)
        if allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Session-Id, X-Conversation-Id")
        self.send_header("Access-Control-Max-Age", "86400")

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        self.send_response(status)
        self._send_security_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _session_id_from_body(self, body: dict[str, Any]) -> str:
        return str(
            self.headers.get("X-Session-Id")
            or self._body_value(body, "sessionId", "session_id", default="default")
            or "default"
        ).strip()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_security_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/health":
            return self._handle_health()
        if self.path.startswith("/api/artifacts/"):
            return self._handle_artifact_serving()
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/chat":
            return self._handle_chat()
        if self.path == "/api/canvas":
            return self._handle_canvas()
        if self.path == "/api/upload":
            return self._handle_upload()
        if self.path == "/api/transcribe":
            return self._handle_transcription()
        self.send_error(404)

    def _handle_health(self) -> None:
        self._write_json(200, {"status": "ok", "configured": handlers.model_is_configured()})

    @staticmethod
    def _body_value(body: dict[str, Any], *names: str, default: Any = None) -> Any:
        for name in names:
            if name in body:
                return body.get(name)
        return default

    def _handle_chat(self) -> None:
        started_at = time.perf_counter()
        try:
            body = self._read_json_body()
        except (ValueError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON body")
            return

        question = str(self._body_value(body, "prompt", "message", "question", default="") or "").strip()
        history = self._body_value(body, "messages", "history", default=[]) or []
        session_id = self._session_id_from_body(body)
        stream = handlers.to_bool(body.get("stream"), default=True)
        mode = str(body.get("mode") or "assistant").strip()
        allow_local_grounding = handlers.to_bool(
            self._body_value(body, "allowLocalGrounding", "allow_local_grounding"),
            default=True,
        )
        attached_files = self._body_value(body, "attachedFiles", "attached_files", default=[]) or []
        direct_files = self._body_value(body, "directFiles", "direct_files", default=[]) or []
        context = self._body_value(body, "context", default=[]) or []

        if stream:
            self._handle_streaming_chat(
                question, history, session_id, mode, allow_local_grounding, attached_files, direct_files, context, started_at
            )
        else:
            self._handle_blocking_chat(
                question, history, session_id, mode, allow_local_grounding, attached_files, direct_files, context, started_at
            )

    def _handle_blocking_chat(
        self, question, history, session_id, mode, allow_local_grounding, attached_files, direct_files, context, started_at
    ):
        decoded_files = handlers.decode_direct_file_payloads(direct_files)
        if decoded_files:
            payload = handlers.answer_from_direct_uploads(
                question, history, decoded_files, session_id=session_id, mode=mode
            )
        elif handlers.is_uploaded_document_request(question):
            context = handlers.get_uploaded_context_for_session(session_id, attached_files) or context
            payload = handlers.answer_from_uploaded_context(
                question, history, context, session_id=session_id, attached_files=attached_files
            )
        else:
            payload = handlers.answer_from_university_knowledge(
                question, history, session_id, attached_files, mode, allow_local_grounding=allow_local_grounding
            )

        self._write_json(200, handlers.with_model_metadata(payload, started_at))

    def _handle_streaming_chat(
        self, question, history, session_id, mode, allow_local_grounding, attached_files, direct_files, context, started_at
    ):
        self.send_response(200)
        self._send_security_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        decoded_files = handlers.decode_direct_file_payloads(direct_files)
        if decoded_files:
            stream = handlers.stream_answer_from_direct_uploads(
                question, history, decoded_files, session_id=session_id, mode=mode
            )
        elif handlers.is_uploaded_document_request(question):
            uploaded_context = handlers.get_uploaded_context_for_session(session_id, attached_files) or context
            payload = handlers.answer_from_uploaded_context(
                question,
                history,
                uploaded_context,
                session_id=session_id,
                attached_files=attached_files,
                mode=mode,
            )
            payload["done"] = True
            stream = iter([payload])
        else:
            stream = handlers.stream_answer_from_university_knowledge(
                question, history, session_id, attached_files, mode, allow_local_grounding=allow_local_grounding
            )

        for chunk in stream:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()

    def _handle_canvas(self) -> None:
        started_at = time.perf_counter()
        try:
            body = self._read_json_body()
        except (ValueError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON body")
            return

        session_id = self._session_id_from_body(body)
        source_content = str(
            self._body_value(body, "sourceContent", "source_content", "content", default="")
            or ""
        ).strip()
        mode = str(body.get("mode") or "assistant").strip()
        title = str(body.get("title") or "").strip()
        allow_local_grounding = handlers.to_bool(
            self._body_value(body, "allowLocalGrounding", "allow_local_grounding"),
            default=True,
        )

        try:
            payload = handlers.create_canvas_website_from_content(
                source_content=source_content,
                session_id=session_id,
                mode=mode,
                title=title,
                allow_local_grounding=allow_local_grounding,
            )
            status = 500 if payload.get("error") else 200
        except Exception as exc:
            payload = {
                "error": str(exc),
                "answer": str(exc),
                "sources": [],
                "artifacts": [],
                "used_model": False,
                "found_match": False,
            }
            status = 500

        self._write_json(status, handlers.with_model_metadata(payload, started_at))

    def _handle_upload(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > handlers.MAX_UPLOAD_BYTES:
                self.send_error(413, "File too large")
                return

            body = self._read_json_body()
            session_id = self._session_id_from_body(body)

            if isinstance(body.get("files"), list):
                results = []
                for item in body.get("files") or []:
                    if not isinstance(item, dict):
                        continue
                    filename = handlers.sanitize_filename(str(item.get("filename") or "upload"))
                    file_data_b64 = str(
                        item.get("content_base64")
                        or item.get("fileData")
                        or item.get("file_data")
                        or ""
                    ).strip()
                    if not file_data_b64:
                        continue
                    file_bytes = base64.b64decode(file_data_b64)
                    results.append(
                        handlers.ingest_upload(
                            session_id,
                            filename,
                            file_bytes,
                            mime_type=item.get("mimeType") or item.get("mime_type"),
                            return_text=handlers.to_bool(body.get("return_text"), default=False),
                        )
                    )

                self._write_json(200, {"ok": True, "files": results})
                return

            filename = handlers.sanitize_filename(str(body.get("filename") or "upload"))
            file_data_b64 = str(body.get("fileData") or body.get("file_data") or body.get("content_base64") or "").strip()

            if not file_data_b64:
                self.send_error(400, "No file data provided")
                return

            file_bytes = base64.b64decode(file_data_b64)
            result = handlers.ingest_upload(
                session_id,
                filename,
                file_bytes,
                mime_type=body.get("mimeType") or body.get("mime_type"),
            )

            self._write_json(200, {"ok": True, "file": result})
        except Exception as exc:
            self._write_json(500, {"ok": False, "error": format_upload_error(exc)})

    def _handle_transcription(self) -> None:
        try:
            body = self._read_json_body()
            audio_b64 = str(body.get("audioData") or body.get("audio_data") or body.get("audio_base64") or "").strip()
            if not audio_b64:
                self.send_error(400, "No audio data")
                return

            audio_bytes = base64.b64decode(audio_b64)
            mime_type = str(body.get("mimeType") or body.get("mime_type") or "audio/webm")
            
            # Using AI_CLIENT from handlers via a helper if needed, but for now we assume handlers has it
            transcript = handlers.AI_CLIENT.transcribe_audio(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
            )

            self._write_json(200, {"ok": True, "transcript": transcript})
        except Exception as exc:
            self.send_error(500, str(exc))

    def _handle_artifact_serving(self) -> None:
        artifact_ref = self.path.removeprefix("/api/artifacts/").split("?")[0].strip("/")
        parts = artifact_ref.split("/", 1)
        if len(parts) != 2:
            self.send_error(404)
            return
        session_token, artifact_id = parts
        if not session_token or not artifact_id or ".." in session_token or ".." in artifact_id:
            self.send_error(403)
            return

        artifact_path = resolve_artifact_path(handlers.CANVAS_ARTIFACTS_DIR, session_token, artifact_id)
        if not artifact_path or not artifact_path.exists():
            self.send_error(404)
            return

        data = artifact_path.read_bytes()
        self.send_response(200)
        self._send_security_headers()
        self.send_header("Content-Type", guess_artifact_mime_type(artifact_path.name))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

def start_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), ChatHandler)
    print(f"DIU Assistant API running on http://{host}:{port}")
    server.serve_forever()
