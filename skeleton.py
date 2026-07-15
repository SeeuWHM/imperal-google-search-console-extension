"""Skeleton context providers for GSC — LLM context cache holding ready
answers. Both degrade to configured:false WITHOUT calling Google when nothing
is connected (never leak errors, never block routing). Lists capped at 5 per
the skeleton contract.
"""
from __future__ import annotations

from app import ext
from accounts import _active_account, gsc_ready
from gsc_api import gsc_list_sites


@ext.skeleton("gsc_config", ttl=300,
              description="Google Search Console connection status — whether the user has connected a Google account")
async def skeleton_gsc_config(ctx) -> dict:
    configured = await gsc_ready(ctx)
    return {"response": {
        "configured": configured,
        "instruction": (
            "Google Search Console not connected — tell the user to call connect_gsc "
            "and authorise their Google account before asking about their sites or "
            "search performance."
            if not configured else
            "Google Search Console is connected. Call list_sites to see the user's properties."
        ),
    }}


@ext.skeleton("gsc_sites", ttl=600,
              description="The user's Search Console properties — site URL and permission level (up to 5 shown)")
async def skeleton_gsc_sites(ctx) -> dict:
    if not await gsc_ready(ctx):
        return {"response": {"configured": False, "sites": [], "total": 0}}
    try:
        rows = await gsc_list_sites(ctx, await _active_account(ctx))
    except Exception as e:
        return {"response": {"configured": True, "sites": [], "total": 0, "error": str(e)}}
    return {"response": {
        "configured": True,
        "sites": [
            {"site_url": r.get("site_url", ""), "permission_level": r.get("permission_level", "")}
            for r in rows[:5]
        ],
        "total": len(rows),
    }}
