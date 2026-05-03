from __future__ import annotations

import numpy as np

from src.apps.documents.rag.pipeline import DocumentChunk


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.rows: dict[str, DocumentChunk] = {}

    def upsert_chunks(self, chunks: list[DocumentChunk], *, session_id: str) -> None:
        for chunk in chunks:
            self.rows[f"{session_id}:{chunk.id}"] = chunk

    def delete_source(self, *, session_id: str, source: str) -> None:
        self.rows = {
            key: chunk
            for key, chunk in self.rows.items()
            if key.split(":", 1)[0] != session_id or chunk.source != source
        }

    def match_chunks(
        self,
        query_embedding: list[float],
        *,
        session_id: str,
        top_k: int,
    ) -> list[DocumentChunk]:
        scored: list[tuple[float, DocumentChunk]] = []
        for key, chunk in self.rows.items():
            row_session_id, _ = key.split(":", 1)
            if row_session_id != session_id:
                continue
            scored.append((_cosine(query_embedding, chunk.embedding), chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for score, chunk in scored[:top_k] if score > 0.04]

    def list_chunks(self, *, session_id: str, limit: int = 1000) -> list[DocumentChunk]:
        chunks = [
            chunk
            for key, chunk in self.rows.items()
            if key.split(":", 1)[0] == session_id
        ]
        return chunks[:limit]

    def count_chunks(self, *, session_id: str) -> int:
        return len(self.list_chunks(session_id=session_id))

    def delete_session(self, *, session_id: str) -> None:
        self.rows = {
            key: chunk
            for key, chunk in self.rows.items()
            if key.split(":", 1)[0] != session_id
        }


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    left_vec = np.array(left, dtype=np.float32)
    right_vec = np.array(right, dtype=np.float32)
    if left_vec.size != right_vec.size:
        return 0.0
    left_norm = np.linalg.norm(left_vec)
    right_norm = np.linalg.norm(right_vec)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left_vec / left_norm, right_vec / right_norm))
