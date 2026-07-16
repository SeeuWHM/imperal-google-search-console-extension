"""GSC · list the user's verified Search Console sites (properties)."""
from __future__ import annotations

import logging

from imperal_sdk.chat.action_result import ActionResult

from app import chat
from gsc_accounts import _active_account, gsc_ready
from gsc_api import gsc_list_sites
from params import EmptyParams
from response_models import SiteList, build_site_list

log = logging.getLogger("gsc_connector")

_NOT_CONNECTED = "Connect your Google account first — call connect_gsc, then authorise Search Console access."


@chat.function(
    "list_sites", action_type="read", data_model=SiteList,
    description=(
        "List the Search Console properties (verified sites) the connected Google account can "
        "access — site URL and permission level. Connect first with connect_gsc. Use for: "
        "покажи мои сайты в search console, какие сайты подключены к гугл, list my gsc sites, "
        "show search console properties, verified google sites."
    ),
)
async def fn_list_sites(ctx, params: EmptyParams) -> ActionResult:
    """List the active Google account's verified Search Console properties."""
    if not await gsc_ready(ctx):
        return ActionResult.error(_NOT_CONNECTED, retryable=False)
    try:
        acc = await _active_account(ctx)
        rows = await gsc_list_sites(ctx, acc)
        return ActionResult.success(
            data=build_site_list(rows),
            summary=(f"{len(rows)} site(s) in Search Console." if rows
                     else "No verified sites on this Google account."),
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)
