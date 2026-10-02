from __future__ import annotations

import ipaddress
import os
import time
from collections import defaultdict, deque
from collections.abc import MutableMapping

from fastapi import HTTPException, Request

_DEFAULT_WINDOW_SECONDS = 3600.0
_DEFAULT_LIMIT = 5
_INTERNAL_CLIENT_HEADER = "x-veridra-client-ip"

PublicRateBuckets = MutableMapping[str, deque[float]]
PUBLIC_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    peer = request.client.host if request.client is not None else "unknown"
    if os.environ.get("VERIDRA_ENV", "").strip().lower() != "production":
        return peer

    forwarded = request.headers.get(_INTERNAL_CLIENT_HEADER, "").strip()
    if not forwarded:
        return peer
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return peer


def enforce_public_rate_limit(
    request: Request,
    *,
    namespace: str,
    limit: int = _DEFAULT_LIMIT,
    window_seconds: float = _DEFAULT_WINDOW_SECONDS,
    buckets: PublicRateBuckets = PUBLIC_RATE_BUCKETS,
) -> None:
    if limit < 1:
        raise ValueError("Public rate limit must be positive.")
    if window_seconds <= 0:
        raise ValueError("Public rate-limit window must be positive.")

    now = time.monotonic()
    key = f"{namespace}:{_client_key(request)}"
    bucket = buckets.setdefault(key, deque())
    while bucket and now - bucket[0] >= window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail="This public audit surface has reached its temporary request limit.",
        )
    bucket.append(now)
