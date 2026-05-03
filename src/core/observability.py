from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_DIR = ROOT / "tmp" / "logs"
DEFAULT_LOG_PATH = DEFAULT_LOG_DIR / "backend_events.jsonl"
DEFAULT_SLOW_REQUEST_MS = 5000
FAILURE_EVENT_TYPES = {
    "chat_error",
    "chat_empty_stream",
    "chat_empty_answer",
    "retrieval_miss",
    "retrieval_weak_match",
}


def get_log_dir() -> Path:
    configured = str(os.getenv("OBS_LOG_DIR", "")).strip()
    return Path(configured) if configured else DEFAULT_LOG_DIR


def get_log_path() -> Path:
    configured = str(os.getenv("OBS_LOG_PATH", "")).strip()
    return Path(configured) if configured else get_log_dir() / DEFAULT_LOG_PATH.name


def get_slow_request_threshold_ms() -> int:
    raw_value = str(os.getenv("OBS_SLOW_REQUEST_MS", DEFAULT_SLOW_REQUEST_MS)).strip()
    try:
        threshold = int(raw_value)
    except ValueError:
        threshold = DEFAULT_SLOW_REQUEST_MS
    return max(threshold, 250)


def normalize_question(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip()).lower()
    return value[:240]


def truncate_text(text: str, *, limit: int = 240) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    return value[:limit]


def log_event(event_type: str, /, **fields: Any) -> None:
    if not event_type:
        return

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **fields,
    }
    log_path = get_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        # Observability should never break the assistant runtime.
        return


def read_events(path: str | Path | None = None) -> list[dict[str, Any]]:
    log_path = Path(path) if path else get_log_path()
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def summarize_events(
    events: list[dict[str, Any]],
    *,
    slow_request_ms: int | None = None,
    top_n: int = 5,
) -> dict[str, Any]:
    threshold = slow_request_ms or get_slow_request_threshold_ms()
    event_counts = Counter()
    failed_questions = Counter()
    slow_questions: dict[str, list[float]] = defaultdict(list)
    recent_failures: list[dict[str, Any]] = []

    for event in events:
        event_type = str(event.get("event") or "").strip()
        if not event_type:
            continue
        event_counts[event_type] += 1

        question = normalize_question(str(event.get("question") or ""))
        elapsed_ms = float(event.get("elapsed_ms") or 0.0)

        if event_type in FAILURE_EVENT_TYPES and question:
            failed_questions[question] += 1
            recent_failures.append(
                {
                    "ts": event.get("ts"),
                    "event": event_type,
                    "question": question,
                    "detail": truncate_text(event.get("error") or event.get("note") or ""),
                }
            )

        if event_type == "chat_complete" and elapsed_ms >= threshold and question:
            slow_questions[question].append(elapsed_ms)

    top_failed_questions = [
        {"question": question, "count": count}
        for question, count in failed_questions.most_common(top_n)
    ]
    top_slow_questions = [
        {
            "question": question,
            "count": len(values),
            "avg_elapsed_ms": round(sum(values) / len(values), 1),
            "max_elapsed_ms": round(max(values), 1),
        }
        for question, values in sorted(
            slow_questions.items(),
            key=lambda item: (len(item[1]), sum(item[1]) / len(item[1])),
            reverse=True,
        )[:top_n]
    ]

    return {
        "total_events": len(events),
        "slow_request_ms": threshold,
        "event_counts": dict(event_counts),
        "top_failed_questions": top_failed_questions,
        "top_slow_questions": top_slow_questions,
        "recent_failures": recent_failures[-top_n:],
    }
