"""GSC · connect (Google OAuth) + connected-account management.

connect_gsc returns the platform-built Google authorisation URL; the gateway
handles the code exchange and writes the account into `gsc_accounts`. The rest
are thin readers/mutators over that collection (same shape as the Google Drive
connector's account handlers, minus the picked-files pool).
"""
from __future__ import annotations

import logging

from imperal_sdk.chat.action_result import ActionResult

from app import chat
from gsc_accounts import (
    ACCOUNTS_COLLECTION, _account_by_email, _account_email, _active_account, _all_accounts,
)
from gsc_api import gsc_list_sites
from params import AccountParam, EmptyParams
from response_models import (
    AccountDisconnected, AccountSwitched, AccountsList, ConnectionStatus, ConnectResult,
    build_accounts_list,
)

log = logging.getLogger("gsc_connector")


@chat.function(
    "connect_gsc", action_type="read", data_model=ConnectResult,
    description=(
        "Start Google Search Console OAuth — returns an authorisation URL to open in the "
        "browser (read-only Search Console access). Connecting again adds another Google "
        "account, each seeing its own sites. Use for: подключи google search console, "
        "подключи гугл серч консоль, привяжи гугл аккаунт, connect google search console, "
        "connect gsc, add another google account, добавь ещё один google аккаунт."
    ),
)
async def fn_connect_gsc(ctx, params: EmptyParams) -> ActionResult:
    """Return a Google OAuth authorisation URL for read-only Search Console."""
    try:
        url = await ctx.oauth_authorize_url("google")
        instruction = (
            "Open the link and authorise read-only Search Console access. After "
            "authorising, call list_sites to see your verified properties."
        )
        return ActionResult.success(
            data=ConnectResult(auth_url=url, instruction=instruction),
            summary="OAuth URL ready — open it to connect Google Search Console.",
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)


@chat.function(
    "connection_status", action_type="read", data_model=ConnectionStatus,
    description=(
        "Whether a Google account is connected to Search Console, how many accounts, and how "
        "many sites the active account can see. Use for: подключён ли search console, "
        "подключён ли гугл, is my google account connected, gsc connection status."
    ),
)
async def fn_connection_status(ctx, params: EmptyParams) -> ActionResult:
    """Report connected-account count and the active account's site count."""
    try:
        accounts = await _all_accounts(ctx)
        emails = [_account_email(a) for a in accounts]
        sites_count = 0
        if accounts:
            try:
                sites_count = len(await gsc_list_sites(ctx, await _active_account(ctx)))
            except Exception:
                sites_count = 0
        return ActionResult.success(
            data=ConnectionStatus(connected=bool(accounts), sites_count=sites_count, accounts=emails),
            summary=(f"{len(accounts)} Google account(s) connected." if accounts else "No Google account connected."),
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)


@chat.function(
    "list_accounts", action_type="read", data_model=AccountsList,
    description=(
        "List the Google accounts connected to Search Console — each account's email and "
        "which one is active. Use for: покажи мои google аккаунты, какие аккаунты search "
        "console подключены, list connected google accounts, which gsc account is active."
    ),
)
async def fn_list_accounts(ctx, params: EmptyParams) -> ActionResult:
    """List connected Google accounts and which one is active."""
    try:
        accounts = await _all_accounts(ctx)
        active_email = _account_email(await _active_account(ctx)) if accounts else ""
        emails = [_account_email(a) for a in accounts]
        return ActionResult.success(
            data=build_accounts_list(emails, active_email),
            summary=f"{len(accounts)} Google account(s) connected." if accounts else "No Google accounts connected.",
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)


@chat.function(
    "switch_account", action_type="write", event="account.switched",
    effects=["update:account"], data_model=AccountSwitched,
    description=(
        "Change the active Google account. Subsequent site and query lookups use this "
        "account until switched again. Use for: переключи google аккаунт, переключи на "
        "другой аккаунт search console, switch google account, use my other gsc account."
    ),
)
async def fn_switch_account(ctx, params: AccountParam) -> ActionResult:
    """Mark one connected account active and the others inactive."""
    try:
        target = await _account_by_email(ctx, params.account)
        for a in await _all_accounts(ctx):
            new_active = a["doc_id"] == target["doc_id"]
            if a.get("is_active") != new_active:
                clean = {k: v for k, v in a.items() if k != "doc_id"}
                await ctx.store.update(ACCOUNTS_COLLECTION, a["doc_id"], {**clean, "is_active": new_active})
        active = _account_email(target)
        return ActionResult.success(
            data=AccountSwitched(active=active), summary=f"Switched to {active}.",
            refresh_panels=["gsc_sidebar"],
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)


@chat.function(
    "disconnect_account", action_type="destructive", event="account.disconnected",
    effects=["delete:account"], data_model=AccountDisconnected,
    description=(
        "Disconnect a Google account from Search Console. Nothing in Google is changed; the "
        "OAuth grant itself can be fully revoked at myaccount.google.com/permissions. Use for: "
        "отключи google аккаунт, убери аккаунт search console, disconnect google account, "
        "remove gsc account."
    ),
)
async def fn_disconnect_account(ctx, params: AccountParam) -> ActionResult:
    """Delete a connected Google account record from the store."""
    try:
        target = await _account_by_email(ctx, params.account)
        email = _account_email(target)
        await ctx.store.delete(ACCOUNTS_COLLECTION, target["doc_id"])
        remaining = len(await _all_accounts(ctx))
        return ActionResult.success(
            data=AccountDisconnected(email=email, remaining=remaining),
            summary=f"Disconnected {email}. {remaining} account(s) remaining.",
            refresh_panels=["gsc_sidebar"],
        )
    except Exception as e:
        return ActionResult.error(str(e), retryable=False)
