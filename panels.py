"""GSC sidebar panel — connect prompt when disconnected; the user's verified
sites when connected. Data is per-user via Google OAuth.

Layout note: action buttons live inside a horizontal Stack so a ghost/primary
button keeps its content width — a lone Button in a vertical Stack renders
full-width (flex align-items:stretch).
"""
from __future__ import annotations

import logging

from imperal_sdk import ui

from app import ext
from accounts import _active_account, gsc_ready
from gsc_api import gsc_list_sites

log = logging.getLogger("gsc_connector")


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
async def sidebar_panel(ctx):
    if not await gsc_ready(ctx):
        return _connect_panel()

    try:
        rows = await gsc_list_sites(ctx, await _active_account(ctx))
    except Exception as e:
        # A connected account whose token/grant no longer works drops back to
        # the connect prompt with the real reason, not a dead-end error card.
        return _connect_panel(error=str(e))

    shown = rows[:12]
    remaining = len(rows) - len(shown)
    list_or_empty = (
        ui.List(items=[
            ui.ListItem(id=r.get("site_url", ""), title=r.get("site_url", "") or "(unknown)",
                        subtitle=r.get("permission_level", ""),
                        on_click=ui.Call("__panel__gsc_workspace", site_url=r.get("site_url", "")))
            for r in shown
        ])
        if shown else
        ui.Text(content="No verified sites on this Google account.", variant="caption")
    )
    footer = (
        [ui.Text(content=f"+ {remaining} more site(s)", variant="caption")]
        if remaining > 0 else []
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
