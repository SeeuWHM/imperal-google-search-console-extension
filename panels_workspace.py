"""GSC center workspace — one site's content opportunities + top queries.

Reuses the analytics impl_ functions server-side (plain Python, zero LLM
tokens) — same two-table shape as se-ranking's workspace (opportunities +
rankings). Opportunities first: striking-distance is the reason to open a site.
"""
from __future__ import annotations

import asyncio

from imperal_sdk import ui

from app import ext
from cache_helpers import ANALYTICS_CACHE_TTL, cached_call
from gsc_accounts import _account_email, _active_account, gsc_ready
from handlers_analytics import impl_striking_distance, impl_top_queries


async def _opportunities_section(ctx, site_url: str) -> ui.UINode:
    try:
        account_key = _account_email(await _active_account(ctx))
        rows = await cached_call(
            ctx, "striking_distance", account_key, {"site_url": site_url}, ANALYTICS_CACHE_TTL,
            lambda: impl_striking_distance(ctx, site_url, days=28, limit=25),
        )
    except Exception as e:
        return ui.Alert(message=str(e), type="error")
    body = ui.DataTable(
        columns=[
            ui.DataColumn(key="query", label="Query", width="55%"),
            ui.DataColumn(key="impressions", label="Impressions", width="22%"),
            ui.DataColumn(key="position", label="Position", width="23%"),
        ],
        rows=[{"query": r["query"], "impressions": r["impressions"], "position": r["position"]} for r in rows],
    ) if rows else ui.Text(content="No striking-distance opportunities for this period.", variant="caption")
    return ui.Stack(gap=1, children=[
        ui.Header(text="Opportunities — almost ranking (position 5-20)", level=5), body,
    ])


_Q_STEP = 25
_Q_MAX = 100   # GSC Search Analytics rowLimit ceiling we expose in the panel


async def _top_queries_section(ctx, site_url: str, q_limit: int = _Q_STEP) -> ui.UINode:
    q_limit = max(_Q_STEP, min(int(q_limit or _Q_STEP), _Q_MAX))
    try:
        account_key = _account_email(await _active_account(ctx))
        rows = await cached_call(
            ctx, "top_queries", account_key, {"site_url": site_url, "q_limit": q_limit}, ANALYTICS_CACHE_TTL,
            lambda: impl_top_queries(ctx, site_url, days=28, limit=q_limit),
        )
    except Exception as e:
        return ui.Alert(message=str(e), type="error")
    body = ui.DataTable(
        columns=[
            ui.DataColumn(key="query", label="Query", width="45%"),
            ui.DataColumn(key="clicks", label="Clicks", width="18%"),
            ui.DataColumn(key="impressions", label="Impressions", width="19%"),
            ui.DataColumn(key="position", label="Position", width="18%"),
        ],
        rows=[{"query": r["query"], "clicks": r["clicks"], "impressions": r["impressions"], "position": r["position"]} for r in rows],
    ) if rows else ui.Text(content="No query data for this site/period yet.", variant="caption")
    children = [ui.Header(text=f"Top queries (last 28 days) — {len(rows)}", level=5), body]
    # Offer "Load more" only when the page came back full (more likely available)
    # and we haven't hit the ceiling — re-render the same panel with a bigger limit.
    if len(rows) >= q_limit and q_limit < _Q_MAX:
        children.append(ui.Button(
            label="Load more queries", variant="ghost", size="sm",
            on_click=ui.Call("__panel__gsc_workspace", site_url=site_url, q_limit=min(q_limit + _Q_STEP, _Q_MAX)),
        ))
    return ui.Stack(gap=1, children=children)


@ext.panel("gsc_workspace", slot="center", title="Search Console", icon="Search",
           refresh="on_event:account.switched,account.disconnected")
async def workspace_panel(ctx, site_url: str = "", q_limit: int = _Q_STEP):
    if not await gsc_ready(ctx):
        return ui.Empty(message="Connect your Google account first — run connect_gsc in chat.")
    if not site_url:
        return ui.Empty(message="Pick a site on the left to see its opportunities and top queries.")

    opportunities, top = await asyncio.gather(
        _opportunities_section(ctx, site_url),
        _top_queries_section(ctx, site_url, q_limit),
    )
    return ui.Stack(children=[opportunities, ui.Divider(), top])
