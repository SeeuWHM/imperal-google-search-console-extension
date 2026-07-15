"""Shared account helpers for the GSC connector.

Per-user connected Google accounts live in the ext_store collection the OAuth
gateway writes to (`gsc_accounts`). Each doc holds access_token / refresh_token
/ expires_at / email / is_active. This module only reads/scopes them — token
refresh lives in token_refresh.py, Google calls in gsc_api.py.
"""
from __future__ import annotations

ACCOUNTS_COLLECTION = "gsc_accounts"


async def _all_accounts(ctx) -> list[dict]:
    docs = await ctx.store.query(ACCOUNTS_COLLECTION)
    out = []
    for d in docs:
        item = dict(d.data)
        item["doc_id"] = d.id
        out.append(item)
    await _hydrate_missing_emails(ctx, out)
    return out


async def _hydrate_missing_emails(ctx, accounts: list[dict]) -> None:
    """The platform's generic OAuth callback fetches an account's email via the
    Gmail profile API for EVERY "google" provider regardless of scope — GSC only
    grants webmasters.readonly/openid/userinfo.email (no Gmail scope), so that
    lookup 403s and every connected account gets persisted as email="unknown".
    Left alone, this collapses every GSC account onto the same store doc on
    upsert (same bug class doc-reader hit with drive.file-only grants). Fetch
    the real address ourselves (covered by the scopes we DO have) and persist
    it once per account. Best-effort — must never break account loading.
    """
    from gsc_api import gsc_userinfo  # local import: avoids a gsc_api<->accounts cycle

    for acc in accounts:
        email = acc.get("email")
        if email and email != "unknown":
            continue  # already has a real address — one-time cost per account
        real = await gsc_userinfo(ctx, acc)
        doc_id = acc.get("doc_id")
        if real and doc_id:
            acc["email"] = real
            await ctx.store.update(ACCOUNTS_COLLECTION, doc_id,
                                    {k: v for k, v in acc.items() if k != "doc_id"})


async def _active_account(ctx) -> dict:
    accounts = await _all_accounts(ctx)
    if not accounts:
        raise RuntimeError("No Google account connected. Call connect_gsc first.")
    return next((a for a in accounts if a.get("is_active")), accounts[0])


def _account_email(acc: dict) -> str:
    """Stable, UNIQUE per-account key. Prefer the real Google address; fall back
    to the store doc id when it's absent or the "unknown" placeholder — otherwise
    accounts without a captured email would collide under one key.
    `_hydrate_missing_emails` fills the real address in for display; this stays
    safe even when that fetch fails."""
    email = acc.get("email")
    if email and email != "unknown":
        return email
    return acc.get("doc_id") or ""


async def _account_by_email(ctx, account: str) -> dict:
    """Resolve a connected account by its email (or store doc id)."""
    accounts = await _all_accounts(ctx)
    match = next((a for a in accounts if a.get("email") == account or a.get("doc_id") == account), None)
    if not match:
        available = [a.get("email") or a.get("doc_id") for a in accounts]
        raise RuntimeError(f"Account {account!r} not found. Connected: {available}")
    return match


async def gsc_ready(ctx) -> bool:
    """True iff the user has at least one connected Google account."""
    try:
        return bool(await _all_accounts(ctx))
    except Exception:
        return False
