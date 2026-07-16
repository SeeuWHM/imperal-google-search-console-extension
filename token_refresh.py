"""Google OAuth token refresh — same pattern as the Google Drive connector's
token_refresh, for the read-only Search Console grant.

The unified gateway does the initial code->token exchange and writes the account
doc. Here we refresh the short-lived access token from our stored refresh_token
whenever it's within 60s of expiry, using the developer-owned client
id/secret app secrets, and persist the new token back to the account doc.
"""
from __future__ import annotations

import time

from constants import ACCOUNTS_COLLECTION

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


async def _refresh_token_if_needed(ctx, acc: dict) -> dict:
    expires_at = acc.get("expires_at") or 0
    if expires_at and int(expires_at) - int(time.time()) > 60:
        return acc
    return await _refresh_google_token(ctx, acc)


async def _refresh_google_token(ctx, acc: dict) -> dict:
    client_id = await ctx.secrets.get("google_client_id")
    client_secret = await ctx.secrets.get("google_client_secret")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Google OAuth credentials not configured (google_client_id/google_client_secret "
            "app secrets are missing — set them from the Google Cloud OAuth client before "
            "this extension can authenticate anyone)."
        )
    refresh_token = acc.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh_token on this account — reconnect via connect_gsc.")

    resp = await ctx.http.post(GOOGLE_TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Google token refresh failed: HTTP {resp.status_code}")

    tokens = resp.json()
    acc["access_token"] = tokens["access_token"]
    acc["expires_at"] = int(time.time()) + int(tokens.get("expires_in", 3600))
    doc_id = acc.get("doc_id")
    if doc_id:
        await ctx.store.update(ACCOUNTS_COLLECTION, doc_id, {k: v for k, v in acc.items() if k != "doc_id"})
    return acc
