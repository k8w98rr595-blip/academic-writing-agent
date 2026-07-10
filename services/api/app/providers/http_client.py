from __future__ import annotations

import asyncio
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
) -> httpx.Response:
    """POST once, with one bounded retry for transient provider failures."""
    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt == attempts - 1:
                return response
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            last_error = error
            if attempt == attempts - 1:
                raise
        await asyncio.sleep(0.05 * (2**attempt))
    if last_error:
        raise last_error
    raise RuntimeError("Provider request ended without a response")
