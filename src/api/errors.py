from __future__ import annotations

import math
import re


def extract_retry_after_seconds(message: str) -> int | None:
    patterns = (
        r'"retryDelay"\s*:\s*"(\d+)s"',
        r"Please retry in ([0-9]+(?:\.[0-9]+)?)s",
    )
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            return max(1, math.ceil(float(match.group(1))))
        except ValueError:
            return None
    return None


def is_daily_free_tier_quota(message: str) -> bool:
    lowered = message.lower()
    return (
        "generaterequestsperdayperprojectpermodel-freetier" in lowered
        or "generate_content_free_tier_requests" in lowered
        or "perdayperprojectpermodel" in lowered
    )


def format_backend_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    is_quota_error = (
        "quota" in lowered
        or "billing" in lowered
        or "resource_exhausted" in lowered
        or "http 429" in lowered
        or extract_retry_after_seconds(message) is not None
    )
    if is_quota_error:
        if is_daily_free_tier_quota(message):
            return (
                "The DIU Assistant service has reached its free daily usage limit for the current project. "
                "Use an API key from a project with available quota, enable billing/increase quota, or wait for the daily reset."
            )
        retry_after = extract_retry_after_seconds(message)
        if retry_after:
            return f"The DIU Assistant service is temporarily rate-limited. Try again in about {retry_after} seconds."
        return "The DIU Assistant service could not answer because the current API project has a quota or billing issue."
    if "api_key_invalid" in lowered or "api key not valid" in lowered or "api key expired" in lowered:
        return "The DIU Assistant service could not authenticate with the current API key. Update the key in GEMINI_API_KEY and restart the API server."
    if "high demand" in lowered or "unavailable" in lowered or "http 503" in lowered:
        return "The DIU Assistant service is temporarily unavailable because the provider is seeing high demand. Try again in a moment."
    return "The assistant backend could not answer right now. Check the API server logs for details."


def format_upload_error(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "Could not extract readable content."
    lowered = message.lower()
    if "gemini api key is not configured" in lowered:
        return "Document extraction needs GEMINI_API_KEY for this file type."
    if "required for" in lowered or "install it with" in lowered:
        return message
    if "image uploads need gemini" in lowered:
        return "Image uploads need GEMINI_API_KEY so the assistant can read the image."
    return message
