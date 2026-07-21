"""Unit tests for gsc_accounts.py — the OAuth-gateway-written account store,
plus token_refresh.py's expiry-aware refresh gate. No network: MockContext +
MockStore + MockHTTP, following the SE Ranking / Bing connectors' convention.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import gsc_accounts as accounts
import token_refresh
from constants import ACCOUNTS_COLLECTION


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore()
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


@pytest.mark.asyncio
async def test_no_accounts_when_nothing_connected():
    ctx = _ctx()
    assert await accounts._all_accounts(ctx) == []
    assert await accounts.gsc_ready(ctx) is False
    with pytest.raises(RuntimeError):
        await accounts._active_account(ctx)


@pytest.mark.asyncio
async def test_single_account_is_active_and_ready():
    ctx = _ctx()
    await _seed(ctx)
    all_accounts = await accounts._all_accounts(ctx)
    assert len(all_accounts) == 1
    assert await accounts.gsc_ready(ctx) is True
    active = await accounts._active_account(ctx)
    assert accounts._account_email(active) == "user@example.com"


@pytest.mark.asyncio
async def test_active_account_prefers_is_active_flag_over_first():
    ctx = _ctx()
    await _seed(ctx, email="a@x.com", is_active=False)
    await _seed(ctx, email="b@x.com", is_active=True)
    active = await accounts._active_account(ctx)
    assert accounts._account_email(active) == "b@x.com"


@pytest.mark.asyncio
async def test_active_account_falls_back_to_first_when_none_flagged_active():
    ctx = _ctx()
    await _seed(ctx, email="a@x.com", is_active=False)
    active = await accounts._active_account(ctx)
    assert accounts._account_email(active) == "a@x.com"


@pytest.mark.asyncio
async def test_account_email_falls_back_to_doc_id_when_unknown():
    acc = {"email": "unknown", "doc_id": "abc123"}
    assert accounts._account_email(acc) == "abc123"
    acc2 = {"email": "", "doc_id": "xyz789"}
    assert accounts._account_email(acc2) == "xyz789"
    acc3 = {"email": "real@x.com", "doc_id": "abc123"}
    assert accounts._account_email(acc3) == "real@x.com"


@pytest.mark.asyncio
async def test_account_by_email_resolves_by_email_or_doc_id():
    ctx = _ctx()
    doc_id = await _seed(ctx, email="a@x.com")
    by_email = await accounts._account_by_email(ctx, "a@x.com")
    assert by_email["doc_id"] == doc_id
    by_doc_id = await accounts._account_by_email(ctx, doc_id)
    assert by_doc_id["doc_id"] == doc_id


@pytest.mark.asyncio
async def test_account_by_email_raises_with_available_list_on_miss():
    ctx = _ctx()
    await _seed(ctx, email="a@x.com")
    with pytest.raises(RuntimeError, match="not found"):
        await accounts._account_by_email(ctx, "nope@x.com")


@pytest.mark.asyncio
async def test_dedupe_by_email_keeps_active_doc_and_drops_duplicates():
    ctx = _ctx()
    # Two docs share the same real email once hydrated — the active/refresh_token
    # one should survive, the stale duplicate should be deleted from the store.
    await _seed(ctx, email="dup@x.com", is_active=False, refresh_token="")
    await _seed(ctx, email="dup@x.com", is_active=True, refresh_token="refresh-2")
    all_accounts = await accounts._all_accounts(ctx)
    assert len(all_accounts) == 1
    assert all_accounts[0]["is_active"] is True


@pytest.mark.asyncio
async def test_gsc_ready_swallows_store_errors():
    class _BrokenStore:
        async def query(self, *a, **kw):
            raise RuntimeError("store down")

    ctx = _ctx()
    ctx.store = _BrokenStore()
    assert await accounts.gsc_ready(ctx) is False


# ─── token_refresh.py ──────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_refresh_token_if_needed_skips_when_far_from_expiry():
    ctx = _ctx()
    acc = {"access_token": "still-good", "expires_at": int(time.time()) + 3600}
    result = await token_refresh._refresh_token_if_needed(ctx, acc)
    assert result["access_token"] == "still-good"


@pytest.mark.asyncio
async def test_refresh_token_if_needed_refreshes_when_near_expiry():
    ctx = _ctx()
    ctx.secrets._store["google_client_id"] = "client-id"
    ctx.secrets._store["google_client_secret"] = "client-secret"
    ctx.http.mock_post("oauth2.googleapis.com/token", {
        "access_token": "fresh-token", "expires_in": 3600,
    })
    acc = {"access_token": "stale", "refresh_token": "refresh-1", "expires_at": int(time.time()) - 10}
    result = await token_refresh._refresh_token_if_needed(ctx, acc)
    assert result["access_token"] == "fresh-token"
    assert result["expires_at"] > int(time.time())


@pytest.mark.asyncio
async def test_refresh_google_token_raises_without_client_credentials():
    ctx = _ctx()
    acc = {"refresh_token": "refresh-1", "expires_at": 0}
    with pytest.raises(RuntimeError, match="not configured"):
        await token_refresh._refresh_google_token(ctx, acc)


@pytest.mark.asyncio
async def test_refresh_google_token_raises_without_refresh_token():
    ctx = _ctx()
    ctx.secrets._store["google_client_id"] = "client-id"
    ctx.secrets._store["google_client_secret"] = "client-secret"
    acc = {"refresh_token": "", "expires_at": 0}
    with pytest.raises(RuntimeError, match="No refresh_token"):
        await token_refresh._refresh_google_token(ctx, acc)


@pytest.mark.asyncio
async def test_refresh_google_token_raises_on_http_error():
    ctx = _ctx()
    ctx.secrets._store["google_client_id"] = "client-id"
    ctx.secrets._store["google_client_secret"] = "client-secret"
    ctx.http.mock_post("oauth2.googleapis.com/token", {"error": "invalid_grant"}, status=400)
    acc = {"refresh_token": "refresh-1", "expires_at": 0}
    with pytest.raises(RuntimeError, match="HTTP 400"):
        await token_refresh._refresh_google_token(ctx, acc)
