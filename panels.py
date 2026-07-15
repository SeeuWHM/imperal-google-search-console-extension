"""GSC sidebar panel — connect prompt when disconnected; the user's verified
sites when connected. Data is per-user via Google OAuth.

Layout note: action buttons live inside a horizontal Stack so a ghost/primary
button keeps its content width — a lone Button in a vertical Stack renders
full-width (flex align-items:stretch).
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from imperal_sdk import ui

from app import ext
from accounts import _active_account, gsc_ready
from gsc_api import gsc_list_sites

log = logging.getLogger("gsc_connector")

_SHOWN_COLLAPSED = 8

# GSC's permissionLevel strings, in plain English.
_PERMISSION_LABELS = {
    "siteOwner": "Owner",
    "siteFullUser": "Full user",
    "siteRestrictedUser": "Restricted user",
    "siteUnverifiedUser": "Unverified",
}


def _parse_site(site_url: str) -> tuple[str, str]:
    """Split a GSC property identifier into (clean domain, connection kind).

    GSC properties come in two shapes: a domain property ("sc-domain:example.com",
    covers every protocol/subdomain/port) or a URL-prefix property
    ("https://www.example.com/", one exact prefix). Both are real GSC concepts
    worth keeping visible — just not as raw "sc-domain:" prefixes — so we show
    the bare domain everywhere and label the connection kind underneath.
    """
    if site_url.startswith("sc-domain:"):
        return site_url[len("sc-domain:"):], "Domain property (all subdomains & protocols)"
    domain = urlparse(site_url).netloc or site_url
    return domain, "URL-prefix property (exact URL only)"


def _connect_panel(error: str = "") -> ui.UINode:
    children = [
        ui.Header(text="Search Console", level=4),
        ui.Badge(label="○ not connected", color="gray"),
        ui.Divider(),
        ui.Text(content=(
            "Connect your Google account to see your Search Console sites and their "
            "real Google Search performance here."
        ), variant="body"),
    ]
    if error:
        children.append(ui.Alert(message=error, type="error"))
    children.append(ui.Stack(direction="h", gap=2, wrap=True, children=[
        ui.Button(label="Connect Google Search Console", icon="Plus", variant="primary",
                  on_click=ui.Call("connect_gsc")),
    ]))
    children.append(ui.Text(
        content="Read-only access (webmasters.readonly) — you choose which Google account to grant.",
        variant="caption",
    ))
    return ui.Stack(children=children)


@ext.panel("gsc_sidebar", slot="left", title="Search Console", icon="Search",
           default_width=260,
           refresh="on_event:account.switched,account.disconnected")
async def sidebar_panel(ctx, show_all: bool = False):
    if not await gsc_ready(ctx):
        return _connect_panel()

    try:
        rows = await gsc_list_sites(ctx, await _active_account(ctx))
    except Exception as e:
        # A connected account whose token/grant no longer works drops back to
        # the connect prompt with the real reason, not a dead-end error card.
        return _connect_panel(error=str(e))

    shown = rows if show_all else rows[:_SHOWN_COLLAPSED]
    remaining = len(rows) - len(shown)
    list_or_empty = (
        ui.List(items=[
            ui.ListItem(
                id=r.get("site_url", ""),
                title=(_parse_site(r.get("site_url", ""))[0] or "(unknown)"),
                subtitle=_PERMISSION_LABELS.get(
                    r.get("permission_level", ""), r.get("permission_level", "") or "Unknown access"
                ),
                on_click=ui.Call("__panel__gsc_workspace", site_url=r.get("site_url", "")),
            )
            for r in shown
        ])
        if shown else
        ui.Text(content="No verified sites on this Google account.", variant="caption")
    )
    footer = (
        [ui.Button(label=f"+ {remaining} more site(s)", variant="ghost", size="sm",
                    on_click=ui.Call("__panel__gsc_sidebar", show_all=True))]
        if remaining > 0 else
        ([ui.Button(label="Show fewer", variant="ghost", size="sm",
                     on_click=ui.Call("__panel__gsc_sidebar", show_all=False))]
         if show_all and len(rows) > _SHOWN_COLLAPSED else [])
    )

    root = ui.Stack(children=[
        ui.Header(text="Search Console", level=4),
        ui.Badge(label="● connected", color="green"),
        ui.Divider(),
        ui.Stats(children=[
            ui.Stat(label="Sites", value=str(len(rows)), icon="Globe"),
        ]),
        ui.Divider(),
        ui.Text(content="Your verified properties — click one to open", variant="caption"),
        list_or_empty,
        *footer,
        ui.Divider(),
        ui.Stack(direction="h", gap=2, wrap=True, children=[
            ui.Button(label="Add Google account", icon="Plus", variant="outline",
                      on_click=ui.Call("connect_gsc")),
        ]),
    ])
    # Claim the center slot so a site click here opens the workspace panel in
    # "center" (not "right") — same fix se-ranking/article-writer needed.
    root.props["auto_action"] = ui.Call("__panel__gsc_workspace").to_dict()
    return root
