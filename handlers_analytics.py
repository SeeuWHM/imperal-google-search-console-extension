"""GSC · Search Analytics — the two highest-value query reports.

top_queries: the connected site's best-performing search queries.
striking_distance: "almost ranking" queries (position 5-20 with real
impressions) — the content/optimisation opportunities. Both read the user's own
Google data via the read-only grant.

impl_* return raw row dicts (reused by the center panel server-side, 0 tokens);
fn_* wrap them as ActionResults for chat.
"""
from __future__ import annotations

import datetime
import logging

from imperal_sdk.chat.action_result import ActionResult

from app import chat
from accounts import _active_account, gsc_ready
from gsc_api import gsc_search_analytics
from params import QueryParams
from response_models import QueryList, build_query_list

log = logging.getLogger("gsc_connector")

_NOT_CONNECTED = "Connect your Google account first — call connect_gsc."

# GSC Search Analytics lags ~2-3 days; end the window 3 days back so the last
# day isn't a mostly-empty partial.
_LAG_DAYS = 3
_STRIKING_MIN_POS = 5.0
_STRIKING_MAX_POS = 20.0
_STRIKING_MIN_IMPRESSIONS = 30
_STRIKING_FETCH = 250   # pull a wide slice, then filter to the striking band client-side


def _date_range(days: int) -> tuple[str, str]:
    end = datetime.date.today() - datetime.timedelta(days=_LAG_DAYS)
    start = end - datetime.timedelta(days=max(1, days))
    return start.isoformat(), end.isoformat()


def _row(r: dict) -> dict:
    keys = r.get("keys") or [""]
    return {
        "query": keys[0] if keys else "",
        "clicks": int(r.get("clicks", 0) or 0),
        "impressions": int(r.get("impressions", 0) or 0),
        "ctr": round(float(r.get("ctr", 0) or 0) * 100, 2),   # API gives a fraction; expose as %
        "position": round(float(r.get("position", 0) or 0), 1),
    }


async def impl_top_queries(ctx, site_url: str, days: int = 28, limit: int = 25) -> list[dict]:
    start, end = _date_range(days)
    body = {"startDate": start, "endDate": end, "dimensions": ["query"], "rowLimit": limit}
    rows = await gsc_search_analytics(ctx, await _active_account(ctx), site_url, body)
    return [_row(r) for r in rows]   # API returns clicks-desc by default


async def impl_striking_distance(ctx, site_url: str, days: int = 28, limit: int = 25) -> list[dict]:
    start, end = _date_range(days)
    body = {"startDate": start, "endDate": end, "dimensions": ["query"], "rowLimit": _STRIKING_FETCH}
    rows = await gsc_search_analytics(ctx, await _active_account(ctx), site_url, body)
    out = [
        _row(r) for r in rows
        if _STRIKING_MIN_POS <= float(r.get("position", 0) or 0) <= _STRIKING_MAX_POS
        and int(r.get("impressions", 0) or 0) >= _STRIKING_MIN_IMPRESSIONS
    ]
    out.sort(key=lambda x: x["impressions"], reverse=True)
    return out[:limit]


@chat.function(
    "top_queries", action_type="read", data_model=QueryList,
    description="The connected site's best-performing Google search queries over the last N days (default 28) — query, clicks, impressions, CTR %, average position. Connect first with connect_gsc.",
)
async def fn_top_queries(ctx, params: QueryParams) -> ActionResult:
    """Top search queries for a site, by clicks."""
    if not await gsc_ready(ctx):
        return ActionResult.error(_NOT_CONNECTED, retryable=False)
    try:
        rows = await impl_top_queries(ctx, params.site_url, params.days, params.limit)
        return ActionResult.success(
            data=build_query_list(params.site_url, rows),
            summary=(f"{len(rows)} top query row(s) for {params.site_url}." if rows
                     else "No query data for this site/period yet."),
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)


@chat.function(
    "striking_distance", action_type="read", data_model=QueryList,
    description="'Almost ranking' queries for the connected site — where it ranks position 5-20 with real impressions (last N days, default 28), sorted by impressions. These are the best article/optimisation opportunities. Connect first with connect_gsc.",
)
async def fn_striking_distance(ctx, params: QueryParams) -> ActionResult:
    """Position 5-20, high-impression queries = content opportunities."""
    if not await gsc_ready(ctx):
        return ActionResult.error(_NOT_CONNECTED, retryable=False)
    try:
        rows = await impl_striking_distance(ctx, params.site_url, params.days, params.limit)
        return ActionResult.success(
            data=build_query_list(params.site_url, rows),
            summary=(f"{len(rows)} opportunity row(s) for {params.site_url}." if rows
                     else "No striking-distance queries for this site/period."),
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)
