from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any

import httpx


RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


async def post_json_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
    attempts: int = 2,
    retry_backoff_seconds: float = 1.0,
    max_retry_after_seconds: float = 5.0,
) -> httpx.Response:
    """POST JSON with bounded transient retries and Retry-After support."""
    return await request_json_with_retry(
        "POST",
        url,
        headers=headers,
        payload=payload,
        timeout_seconds=timeout_seconds,
        attempts=attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        max_retry_after_seconds=max_retry_after_seconds,
    )


async def get_json_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    timeout_seconds: int,
    attempts: int = 2,
    retry_backoff_seconds: float = 1.0,
    max_retry_after_seconds: float = 5.0,
) -> httpx.Response:
    return await request_json_with_retry(
        "GET",
        url,
        headers=headers,
        payload=None,
        timeout_seconds=timeout_seconds,
        attempts=attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        max_retry_after_seconds=max_retry_after_seconds,
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after", "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            target = parsedate_to_datetime(raw)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


async def request_json_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout_seconds: int,
    attempts: int = 2,
    retry_backoff_seconds: float = 1.0,
    max_retry_after_seconds: float = 5.0,
) -> httpx.Response:
    """Make a bounded JSON request without logging headers, bodies, or responses."""
    if attempts < 1 or attempts > 3:
        raise ValueError("Provider attempts must be between 1 and 3")
    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.request(method, url, headers=headers, json=payload)
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt == attempts - 1:
                return response
            retry_after = _retry_after_seconds(response)
            if retry_after is not None and retry_after > max_retry_after_seconds:
                return response
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            last_error = error
            if attempt == attempts - 1:
                raise
            retry_after = None
        delay = retry_after if retry_after is not None else retry_backoff_seconds * (2**attempt)
        await asyncio.sleep(min(delay, max_retry_after_seconds))
    if last_error:
        raise last_error
    raise RuntimeError("Provider request ended without a response")
