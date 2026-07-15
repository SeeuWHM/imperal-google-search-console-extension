"""GSC center workspace — one site's content opportunities + top queries.

Reuses the analytics impl_ functions server-side (plain Python, zero LLM
tokens) — same two-table shape as se-ranking's workspace (opportunities +
rankings). Opportunities first: striking-distance is the reason to open a site.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from gsc_accounts import gsc_ready
from handlers_analytics import impl_striking_distance, impl_top_queries


async def _opportunities_section(ctx, site_url: str) -> ui.UINode:
    try:
        rows = await impl_striking_distance(ctx, site_url, days=28, limit=25)
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


async def _top_queries_section(ctx, site_url: str) -> ui.UINode:
    try:
        rows = await impl_top_queries(ctx, site_url, days=28, limit=25)
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
    return ui.Stack(gap=1, children=[
        ui.Header(text="Top queries (last 28 days)", level=5), body,
    ])


@ext.panel("gsc_workspace", slot="center", title="Search Console", icon="Search")
async def workspace_panel(ctx, site_url: str = ""):
    if not await gsc_ready(ctx):
        return ui.Empty(message="Connect your Google account first — run connect_gsc in chat.")
    if not site_url:
        return ui.Empty(message="Pick a site on the left to see its opportunities and top queries.")

    opportunities, top = (
        await _opportunities_section(ctx, site_url),
        await _top_queries_section(ctx, site_url),
    )
    return ui.Stack(children=[opportunities, ui.Divider(), top])
