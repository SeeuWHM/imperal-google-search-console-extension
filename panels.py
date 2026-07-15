"""GSC sidebar panel — connect prompt when disconnected; connected accounts +
the active account's verified sites when connected. Data is per-user via
Google OAuth, one Google account at a time can be active but many can be
connected simultaneously (see accounts block below).

Layout note: action buttons live inside a horizontal Stack so a ghost/primary
button keeps its content width — a lone Button in a vertical Stack renders
full-width (flex align-items:stretch).
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from imperal_sdk import ui

from app import ext
from gsc_accounts import _account_email, _active_account, _all_accounts, gsc_ready
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


async def _account_items(ctx, accounts: list[dict], active_email: str) -> list[ui.UINode]:
    items = []
    for acc in accounts:
        email = _account_email(acc)
        is_active = email == active_email
        items.append(ui.ListItem(
            id=email, title=email,
            subtitle="✓ Active" if is_active else "Click to switch",
            avatar=ui.Avatar(fallback=email[0].upper() if email else "?", size="sm"),
            badge=ui.Badge("✓", color="green") if is_active else None,
            on_click=None if is_active else ui.Call("switch_account", account=email),
            actions=[{"label": "Disconnect", "icon": "Trash2",
                      "on_click": ui.Call("disconnect_account", account=email)}],
        ))
    return items


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
        content="Read-only access (webmasters.readonly) — you choose which Google account to grant. "
                "You can connect more than one account and switch between them below.",
        variant="caption",
    ))
    return ui.Stack(children=children)


@ext.panel("gsc_sidebar", slot="left", title="Search Console", icon="Search",
           default_width=260,
           refresh="on_event:account.switched,account.disconnected")
async def sidebar_panel(ctx, show_all: bool = False):
    if not await gsc_ready(ctx):
        return _connect_panel()

    accounts = await _all_accounts(ctx)
    active = await _active_account(ctx)
    active_email = _account_email(active)

    try:
        rows = await gsc_list_sites(ctx, active)
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

    # Account selector — every connected Google account, active one marked,
    # click any other to switch. This was the missing piece: with only one
    # account ever rendered, a second "Connect" had nowhere to show up.
    account_items = await _account_items(ctx, accounts, active_email)

    # Build the OAuth URL server-side so the button can ui.Open it directly
    # (ui.Call would surface the URL as a toast instead of opening it).
    try:
        auth_url = await ctx.oauth_authorize_url("google")
        add_account_btn = ui.Button(label="Add another Google account", icon="Plus", variant="outline",
                                     on_click=ui.Open(auth_url))
    except Exception as e:
        add_account_btn = ui.Alert(message=f"Couldn't build the connect link: {e}", type="warning")

    root = ui.Stack(children=[
        ui.Header(text="Search Console", level=4),
        ui.Badge(label="● connected", color="green"),
        ui.Divider(),
        ui.Text(content=f"Accounts ({len(accounts)})", variant="caption"),
        ui.List(items=account_items) if account_items else ui.Empty(message="No accounts"),
        ui.Stack(direction="h", gap=2, wrap=True, children=[add_account_btn]),
        ui.Divider(),
        ui.Stats(children=[
            ui.Stat(label="Sites", value=str(len(rows)), icon="Globe"),
        ]),
        ui.Divider(),
        ui.Text(content=f"{active_email}'s verified properties — click one to open", variant="caption"),
        list_or_empty,
        *footer,
    ])
    # Claim the center slot so a site click here opens the workspace panel in
    # "center" (not "right") — same fix se-ranking/article-writer needed.
    root.props["auto_action"] = ui.Call("__panel__gsc_workspace").to_dict()
    return root
