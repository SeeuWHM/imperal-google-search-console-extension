"""Thin wrappers over the Google Search Console REST API — one primitive per
operation, no orchestration baked in here. All calls go directly to
googleapis.com via ctx.http with the user's own OAuth access token (refreshed
on demand). Base: webmasters/v3.
"""
from __future__ import annotations

from urllib.parse import quote

from token_refresh import _refresh_token_if_needed

WEBMASTERS_API = "https://www.googleapis.com/webmasters/v3"
USERINFO_API = "https://openidconnect.googleapis.com/v1/userinfo"


async def _bearer(ctx, acc: dict) -> tuple[dict, dict]:
    """Refresh if needed, return (account, Authorization header dict)."""
    acc = await _refresh_token_if_needed(ctx, acc)
    return acc, {"Authorization": f"Bearer {acc['access_token']}"}


async def gsc_userinfo(ctx, acc: dict) -> str | None:
    """The connected account's real Google address.

    The platform's generic OAuth callback resolves an account's email via the
    Gmail profile API for EVERY "google" provider, regardless of which scopes
    the extension actually declared (see auth-gateway's unified-ext-oauth-connect
    design). GSC only grants webmasters.readonly + openid + userinfo.email — no
    Gmail scope — so that lookup 403s and the platform persists email="unknown"
    for every account. Fetch it ourselves from the OIDC userinfo endpoint, which
    IS covered by the openid/userinfo.email scopes this extension declares.
    Best-effort: returns None on any failure, never raises.
    """
    try:
        acc, headers = await _bearer(ctx, acc)
        resp = await ctx.http.get(USERINFO_API, headers=headers)
        if resp.status_code != 200:
            return None
        return (resp.json() or {}).get("email") or None
    except Exception:
        return None


async def gsc_list_sites(ctx, acc: dict) -> list[dict]:
    """The connected account's verified GSC properties.

    Returns [{"site_url", "permission_level"}]. site_url is either a URL-prefix
    property ("https://example.com/") or a domain property ("sc-domain:example.com").
    """
    acc, headers = await _bearer(ctx, acc)
    resp = await ctx.http.get(f"{WEBMASTERS_API}/sites", headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Google Search Console error listing sites: HTTP {resp.status_code}")
    entries = (resp.json() or {}).get("siteEntry") or []
    return [
        {"site_url": e.get("siteUrl", ""), "permission_level": e.get("permissionLevel", "")}
        for e in entries
    ]


async def gsc_search_analytics(ctx, acc: dict, site_url: str, body: dict) -> list[dict]:
    """Search Analytics query rows for one property (Phase 2 data functions
    build the `body`: startDate/endDate/dimensions/dimensionFilterGroups/rowLimit
    /type/dataState). Each row: {keys:[...], clicks, impressions, ctr, position}.
    site_url is URL-encoded into the path (raw ':' and '/' would break it)."""
    acc, headers = await _bearer(ctx, acc)
    path = f"{WEBMASTERS_API}/sites/{quote(site_url, safe='')}/searchAnalytics/query"
    resp = await ctx.http.post(path, json=body, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Google Search Console error querying analytics: HTTP {resp.status_code}")
    return (resp.json() or {}).get("rows") or []
