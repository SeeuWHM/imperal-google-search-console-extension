"""End-to-end unit tests for every GSC chat function (handlers_connect,
handlers_sites, handlers_analytics). No network: MockContext + MockStore +
MockHTTP. Mirrors the coverage depth of bing-webmaster-connector's
tests/test_handlers.py.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext

import handlers_analytics as analytics
import handlers_connect as connect
import handlers_sites as sites
from constants import ACCOUNTS_COLLECTION
from params import AccountParam, EmptyParams, QueryParams
from imperal_sdk.testing.mock_secrets import MockSecretStore


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"google_client_id": "client-id", "google_client_secret": "client-secret"})
    return ctx


async def _seed(ctx, **fields) -> str:
    defaults = {
        "email": "user@example.com",
        "is_active": True,
        "access_token": "tok-1",
        "refresh_token": "refresh-1",
        "expires_at": int(time.time()) + 3600,
    }
    defaults.update(fields)
    doc = await ctx.store.create(ACCOUNTS_COLLECTION, defaults)
    return doc.id


# ─── connect_gsc ──────────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_connect_gsc_returns_auth_url(monkeypatch):
    # ctx.oauth_authorize_url signs its `state` with IMPERAL_OAUTH_STATE_SECRET (kernel-side
    # env var in real deployments) — set it here so the unit test exercises the real code path
    # instead of mocking oauth_authorize_url away.
    monkeypatch.setenv("IMPERAL_OAUTH_STATE_SECRET", "test-signing-secret")
    ctx = _ctx()
    result = await connect.fn_connect_gsc(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.auth_url


# ─── connection_status ────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_connection_status_reports_disconnected():
    ctx = _ctx()
    result = await connect.fn_connection_status(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.connected is False
    assert result.data.accounts == []


@pytest.mark.asyncio
async def test_connection_status_reports_connected_with_sites():
    ctx = _ctx()
    await _seed(ctx)
    ctx.http.mock_get("webmasters/v3/sites", {
        "siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}],
    })
    result = await connect.fn_connection_status(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.connected is True
    assert result.data.sites_count == 1
    assert result.data.accounts == ["user@example.com"]


# ─── list_accounts ────────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_list_accounts_empty():
    ctx = _ctx()
    result = await connect.fn_list_accounts(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.count == 0


@pytest.mark.asyncio
async def test_list_accounts_marks_active():
    ctx = _ctx()
    await _seed(ctx, email="a@x.com", is_active=False)
    await _seed(ctx, email="b@x.com", is_active=True)
    result = await connect.fn_list_accounts(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.count == 2
    active = [a for a in result.data.accounts if a.is_active]
    assert len(active) == 1
    assert active[0].email == "b@x.com"


# ─── switch_account ───────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_switch_account_flips_active_flag_and_refreshes_sidebar():
    ctx = _ctx()
    await _seed(ctx, email="a@x.com", is_active=True)
    await _seed(ctx, email="b@x.com", is_active=False)
    result = await connect.fn_switch_account(ctx, AccountParam(account="b@x.com"))
    assert result.status == "success"
    assert result.data.active == "b@x.com"
    assert result.refresh_panels == ["gsc_sidebar"]

    docs = await ctx.store.query(ACCOUNTS_COLLECTION)
    by_email = {d.data["email"]: d.data["is_active"] for d in docs.data}
    assert by_email == {"a@x.com": False, "b@x.com": True}


@pytest.mark.asyncio
async def test_switch_account_unknown_email_errors():
    ctx = _ctx()
    await _seed(ctx, email="a@x.com")
    result = await connect.fn_switch_account(ctx, AccountParam(account="nope@x.com"))
    assert result.status == "error"


# ─── disconnect_account ───────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_disconnect_account_removes_it_and_refreshes_sidebar():
    ctx = _ctx()
    await _seed(ctx, email="a@x.com")
    result = await connect.fn_disconnect_account(ctx, AccountParam(account="a@x.com"))
    assert result.status == "success"
    assert result.data.email == "a@x.com"
    assert result.data.remaining == 0
    assert result.refresh_panels == ["gsc_sidebar"]
    after = await connect.fn_list_accounts(ctx, EmptyParams())
    assert after.data.count == 0


@pytest.mark.asyncio
async def test_disconnect_account_unknown_email_errors():
    ctx = _ctx()
    result = await connect.fn_disconnect_account(ctx, AccountParam(account="ghost@x.com"))
    assert result.status == "error"


# ─── list_sites ───────────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_list_sites_not_connected():
    ctx = _ctx()
    result = await sites.fn_list_sites(ctx, EmptyParams())
    assert result.status == "error"


@pytest.mark.asyncio
async def test_list_sites_returns_properties():
    ctx = _ctx()
    await _seed(ctx)
    ctx.http.mock_get("webmasters/v3/sites", {
        "siteEntry": [
            {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
            {"siteUrl": "https://www.example.com/", "permissionLevel": "siteFullUser"},
        ],
    })
    result = await sites.fn_list_sites(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.count == 2
    assert {s.site_url for s in result.data.sites} == {"sc-domain:example.com", "https://www.example.com/"}


# ─── top_queries / striking_distance ──────────────────────────────────────── #

_ANALYTICS_ROWS = {
    "rows": [
        {"keys": ["hosting"], "clicks": 100, "impressions": 500, "ctr": 0.2, "position": 2.0},
        {"keys": ["cheap hosting"], "clicks": 5, "impressions": 300, "ctr": 0.017, "position": 8.0},
        {"keys": ["free hosting"], "clicks": 1, "impressions": 50, "ctr": 0.02, "position": 25.0},
        {"keys": ["low impressions"], "clicks": 0, "impressions": 3, "ctr": 0.0, "position": 6.0},
    ],
}


@pytest.mark.asyncio
async def test_top_queries_not_connected():
    ctx = _ctx()
    result = await analytics.fn_top_queries(ctx, QueryParams(site_url="https://example.com/"))
    assert result.status == "error"


@pytest.mark.asyncio
async def test_top_queries_maps_rows_in_api_order():
    ctx = _ctx()
    await _seed(ctx)
    ctx.http.mock_post("searchAnalytics/query", _ANALYTICS_ROWS)
    result = await analytics.fn_top_queries(ctx, QueryParams(site_url="https://example.com/", limit=25))
    assert result.status == "success"
    assert [r.query for r in result.data.rows] == ["hosting", "cheap hosting", "free hosting", "low impressions"]
    assert result.data.rows[0].clicks == 100


@pytest.mark.asyncio
async def test_striking_distance_filters_to_position_band_and_min_impressions():
    ctx = _ctx()
    await _seed(ctx)
    ctx.http.mock_post("searchAnalytics/query", _ANALYTICS_ROWS)
    result = await analytics.fn_striking_distance(ctx, QueryParams(site_url="https://example.com/", limit=25))
    assert result.status == "success"
    # "hosting" (pos 2.0) is outside the 4-20 band; "free hosting" (pos 25.0) is
    # outside too; "low impressions" (3 impressions) is below the min-10 floor.
    # Only "cheap hosting" (pos 8.0, 300 impressions) survives.
    assert [r.query for r in result.data.rows] == ["cheap hosting"]


@pytest.mark.asyncio
async def test_striking_distance_sorted_by_impressions_desc():
    ctx = _ctx()
    await _seed(ctx)
    ctx.http.mock_post("searchAnalytics/query", {
        "rows": [
            {"keys": ["low"], "clicks": 1, "impressions": 50, "ctr": 0.02, "position": 10.0},
            {"keys": ["high"], "clicks": 2, "impressions": 900, "ctr": 0.002, "position": 12.0},
        ],
    })
    result = await analytics.fn_striking_distance(ctx, QueryParams(site_url="https://example.com/", limit=25))
    assert [r.query for r in result.data.rows] == ["high", "low"]


@pytest.mark.asyncio
async def test_striking_distance_respects_limit():
    ctx = _ctx()
    await _seed(ctx)
    rows = [
        {"keys": [f"q{i}"], "clicks": 1, "impressions": 100 + i, "ctr": 0.01, "position": 10.0}
        for i in range(30)
    ]
    ctx.http.mock_post("searchAnalytics/query", {"rows": rows})
    result = await analytics.fn_striking_distance(ctx, QueryParams(site_url="https://example.com/", limit=5))
    assert len(result.data.rows) == 5
