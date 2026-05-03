from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://localhost:5174,"
    "http://127.0.0.1:5174"
)


def get_allowed_origin_patterns() -> list[str]:
    raw_value = os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [
        item.strip()
        for item in str(raw_value).split(",")
        if item.strip()
    ]


def origin_is_allowed(origin: str | None, patterns: list[str] | None = None) -> bool:
    return resolve_allowed_origin(origin, patterns) is not None


def resolve_allowed_origin(origin: str | None, patterns: list[str] | None = None) -> str | None:
    normalized = str(origin or "").strip()
    candidates = patterns or get_allowed_origin_patterns()
    if not candidates:
        return None
    if "*" in candidates:
        return "*"
    if not normalized:
        return None

    try:
        parsed = urlparse(normalized)
        scheme = parsed.scheme
        host = parsed.hostname or ""
    except Exception:
        return None

    for pattern in candidates:
        if pattern == normalized:
            return normalized
        wildcard_prefix = f"{scheme}://*."
        if pattern.startswith(wildcard_prefix):
            suffix = pattern.removeprefix(wildcard_prefix)
            if host == suffix:
                continue
            if host.endswith(f".{suffix}"):
                return normalized
    return None


def load_local_env(env_path: str | Path) -> None:
    """Load simple KEY=VALUE pairs from a local .env file into the process."""
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            # Keep already-exported values higher priority than the local file.
            os.environ.setdefault(key, value)
