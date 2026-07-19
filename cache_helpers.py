"""ctx.cache wrapper for GSC's panel reads.

The sidebar (site list) and workspace (striking-distance + top-queries)
panels used to call the live googleapis.com Search Analytics API on every
single render — 1-3 real HTTP round-trips (with on-demand OAuth token
refresh) each time a panel opened or a "Load more" button was clicked.
Search Console data itself lags 2-3 days behind reality (see
handlers_analytics._LAG_DAYS), so there is zero freshness cost to caching
it for a couple of minutes - only a big win on repeat panel opens.

ctx.cache TTL is platform-capped to [5, 300]s (I-CACHE-TTL-CAP-300S).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class CachedGscPayload(BaseModel):
    """Generic ctx.cache envelope — one JSON-serialisable payload per call."""
    data: Any = Field(default_factory=list)


SITES_CACHE_TTL = 120     # verified-sites list rarely changes
ANALYTICS_CACHE_TTL = 180  # striking-distance / top-queries (2-3 day lag anyway)


def _cache_key(scope: str, account_key: str, extra: dict | None = None) -> str:
    parts = {"scope": scope, "account": account_key, "extra": extra or {}}
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]
    return f"gsc:{digest}"


async def cached_call(ctx, scope: str, account_key: str, extra: dict | None,
                       ttl_seconds: int, fetcher: Callable[[], Awaitable[Any]]) -> Any:
    """Cache one JSON-serialisable payload behind ctx.cache.get_or_fetch().

    Falls back to calling the fetcher directly if ctx.cache is unavailable
    (e.g. a minimal test/mock Context) so callers never have to special-case it.
    """
    key = _cache_key(scope, account_key, extra)

    async def _fetch() -> CachedGscPayload:
        return CachedGscPayload(data=await fetcher())

    try:
        cache = ctx.cache
    except Exception:
        return await fetcher()

    result = await cache.get_or_fetch(key, CachedGscPayload, _fetch, ttl_seconds=ttl_seconds)
    return result.data
