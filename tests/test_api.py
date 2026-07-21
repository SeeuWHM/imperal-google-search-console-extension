"""Unit tests for gsc_api.py — thin wrappers over the GSC REST API. No real
network: MockContext + MockHTTP intercepts every googleapis.com call.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext

import gsc_api

_FRESH_ACC = {"access_token": "tok-1", "refresh_token": "refresh-1", "expires_at": int(time.time()) + 3600}


def _ctx() -> MockContext:
    return MockContext(user_id="tenant-abc-123")


@pytest.mark.asyncio
async def test_gsc_userinfo_returns_email_on_success():
    ctx = _ctx()
    ctx.http.mock_get("openidconnect.googleapis.com/v1/userinfo", {"email": "real@example.com"})
    email = await gsc_api.gsc_userinfo(ctx, dict(_FRESH_ACC))
    assert email == "real@example.com"


@pytest.mark.asyncio
async def test_gsc_userinfo_returns_none_on_http_error():
    ctx = _ctx()
    ctx.http.mock_get("openidconnect.googleapis.com/v1/userinfo", {"error": "forbidden"}, status=403)
    email = await gsc_api.gsc_userinfo(ctx, dict(_FRESH_ACC))
    assert email is None


@pytest.mark.asyncio
async def test_gsc_userinfo_returns_none_on_exception():
    ctx = _ctx()
    # No mock registered at all -> MockHTTP._find returns 404, handled gracefully.
    email = await gsc_api.gsc_userinfo(ctx, dict(_FRESH_ACC))
    assert email is None


@pytest.mark.asyncio
async def test_gsc_list_sites_maps_site_entries():
    ctx = _ctx()
    ctx.http.mock_get("webmasters/v3/sites", {
        "siteEntry": [
            {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
            {"siteUrl": "https://www.example.com/", "permissionLevel": "siteFullUser"},
        ]
    })
    rows = await gsc_api.gsc_list_sites(ctx, dict(_FRESH_ACC))
    assert rows == [
        {"site_url": "sc-domain:example.com", "permission_level": "siteOwner"},
        {"site_url": "https://www.example.com/", "permission_level": "siteFullUser"},
    ]


@pytest.mark.asyncio
async def test_gsc_list_sites_empty_when_no_site_entry_key():
    ctx = _ctx()
    ctx.http.mock_get("webmasters/v3/sites", {})
    rows = await gsc_api.gsc_list_sites(ctx, dict(_FRESH_ACC))
    assert rows == []


@pytest.mark.asyncio
async def test_gsc_list_sites_raises_on_http_error():
    ctx = _ctx()
    ctx.http.mock_get("webmasters/v3/sites", {"error": "unauthorized"}, status=401)
    with pytest.raises(RuntimeError, match="HTTP 401"):
        await gsc_api.gsc_list_sites(ctx, dict(_FRESH_ACC))


@pytest.mark.asyncio
async def test_gsc_search_analytics_returns_rows():
    ctx = _ctx()
    ctx.http.mock_post("searchAnalytics/query", {
        "rows": [{"keys": ["hello world"], "clicks": 5, "impressions": 100, "ctr": 0.05, "position": 6.2}]
    })
    rows = await gsc_api.gsc_search_analytics(ctx, dict(_FRESH_ACC), "sc-domain:example.com", {"startDate": "2026-01-01"})
    assert rows == [{"keys": ["hello world"], "clicks": 5, "impressions": 100, "ctr": 0.05, "position": 6.2}]


@pytest.mark.asyncio
async def test_gsc_search_analytics_empty_when_no_rows_key():
    ctx = _ctx()
    ctx.http.mock_post("searchAnalytics/query", {})
    rows = await gsc_api.gsc_search_analytics(ctx, dict(_FRESH_ACC), "sc-domain:example.com", {})
    assert rows == []


@pytest.mark.asyncio
async def test_gsc_search_analytics_raises_on_http_error():
    ctx = _ctx()
    ctx.http.mock_post("searchAnalytics/query", {"error": "quota exceeded"}, status=429)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        await gsc_api.gsc_search_analytics(ctx, dict(_FRESH_ACC), "sc-domain:example.com", {})


@pytest.mark.asyncio
async def test_gsc_search_analytics_url_encodes_site_url():
    """A domain property like 'sc-domain:example.com' contains ':' which MUST be
    percent-encoded in the path — an un-encoded ':' breaks Google's routing."""
    ctx = _ctx()
    captured = {}
    orig_post = ctx.http.post

    async def spy_post(url, **kwargs):
        captured["url"] = url
        return await orig_post(url, **kwargs)

    ctx.http.post = spy_post
    ctx.http.mock_post("searchAnalytics/query", {"rows": []})
    await gsc_api.gsc_search_analytics(ctx, dict(_FRESH_ACC), "sc-domain:example.com", {})
    assert "sc-domain%3Aexample.com" in captured["url"]
    assert ":" not in captured["url"].split("/sites/")[1].split("/searchAnalytics")[0]
