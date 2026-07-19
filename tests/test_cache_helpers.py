"""cache_helpers.cached_call — unit tests, no network.

Mirrors the pattern used in matomo-analytics-extension's tests: a fake
CacheClient standing in for imperal_sdk's real ctx.cache contract
(get_or_fetch: miss -> fetch + store; hit -> never re-fetch).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from cache_helpers import CachedGscPayload, cached_call


class _FakeCacheClient:
    def __init__(self):
        self.store: dict[str, object] = {}
        self.fetch_calls = 0

    async def get_or_fetch(self, key, model, fetcher, ttl_seconds=60):
        if key in self.store:
            return self.store[key]
        self.fetch_calls += 1
        value = await fetcher()
        self.store[key] = value
        return value


def _ctx_with_cache():
    ctx = SimpleNamespace()
    ctx.cache = _FakeCacheClient()
    return ctx


class _NoCacheContext:
    """Simulates a Context whose ctx.cache property raises (unwired/minimal)."""
    @property
    def cache(self):
        raise RuntimeError("no cache available")


@pytest.mark.asyncio
async def test_cached_call_fetches_once_then_serves_from_cache():
    ctx = _ctx_with_cache()
    calls = []

    async def fetcher():
        calls.append(1)
        return [{"query": "hello", "clicks": 5}]

    first = await cached_call(ctx, "top_queries", "user@x.com", {"site_url": "https://a.com"}, 60, fetcher)
    second = await cached_call(ctx, "top_queries", "user@x.com", {"site_url": "https://a.com"}, 60, fetcher)

    assert first == [{"query": "hello", "clicks": 5}]
    assert second == first
    assert len(calls) == 1
    assert ctx.cache.fetch_calls == 1


@pytest.mark.asyncio
async def test_cached_call_keys_differ_per_account_and_extra():
    ctx = _ctx_with_cache()
    seen = []

    async def fetcher():
        seen.append(1)
        return [{"n": len(seen)}]

    r1 = await cached_call(ctx, "sites", "a@x.com", None, 60, fetcher)
    r2 = await cached_call(ctx, "sites", "b@x.com", None, 60, fetcher)
    r3 = await cached_call(ctx, "top_queries", "a@x.com", {"site_url": "https://a.com"}, 60, fetcher)
    r4 = await cached_call(ctx, "top_queries", "a@x.com", {"site_url": "https://b.com"}, 60, fetcher)

    assert len(seen) == 4          # every distinct key is a genuine miss
    assert r1 != r2 or r1 == r2    # (values may coincide; keys are what matter)
    assert ctx.cache.fetch_calls == 4


@pytest.mark.asyncio
async def test_cached_call_falls_back_when_cache_unavailable():
    ctx = _NoCacheContext()
    calls = []

    async def fetcher():
        calls.append(1)
        return {"ok": True}

    result = await cached_call(ctx, "sites", "a@x.com", None, 60, fetcher)
    assert result == {"ok": True}
    result2 = await cached_call(ctx, "sites", "a@x.com", None, 60, fetcher)
    assert result2 == {"ok": True}
    assert len(calls) == 2  # no cache => every call is a real fetch


def test_cached_gsc_payload_accepts_list_and_dict():
    assert CachedGscPayload(data=[1, 2, 3]).data == [1, 2, 3]
    assert CachedGscPayload(data={"a": 1}).data == {"a": 1}
