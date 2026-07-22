"""Google Search Console — Extension init (SDK 5.9.x, per-user Google OAuth).

Each user connects their OWN Google account (read-only Search Console scope)
and sees their OWN verified sites/properties. Mirrors the working Google OAuth
plumbing of the Google Drive connector: the unified platform gateway does the
code->token exchange and writes the account doc into the `gsc_accounts`
collection; this extension reads it, refreshes the access token itself
(token_refresh.py), and calls the GSC REST API directly (gsc_api.py). No
microservice — GSC is Google's own API, per-user OAuth, generous quotas.
"""
from __future__ import annotations

import logging

from imperal_sdk import Extension, ChatExtension

log = logging.getLogger("gsc_connector")

ext = Extension(
    "google-search-console-connector",
    version="0.5.1",
    display_name="Google Search Console",
    description=(
        "Connect your own Google account to see your Search Console properties and "
        "their real Google Search performance — top queries, impressions, clicks and "
        "average position, straight from Google."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=["store:read", "store:write", "secrets:read"],
)

chat = ChatExtension(
    ext,
    tool_name="tool_gsc_chat",
    description=(
        "Google Search Console — the user's own Google Search performance data. Use "
        "for: connecting a Google account (connect_gsc), listing the user's verified "
        "sites (list_sites), and managing which connected account is active. Data is "
        "read-only and scoped to the accounts the user grants."
    ),
    max_rounds=10,
)

# ── OAuth — unified platform OAuth (gateway handles code exchange + storage) ──
# Provider key MUST be "google": ctx.oauth_authorize_url() only knows
# google/microsoft/yahoo (hardcoded authorize endpoints) and reads the app
# secret {provider}_client_id, i.e. "google_client_id". A custom key raises at
# runtime and looks up a non-existent secret. The callback route is
#   https://panel.imperal.io/v1/ext/google-search-console-connector/oauth/google/callback
# derived from the app_id "google-search-console-connector" (the Dev Portal app
# id — NOT the git repo name). Register THAT exact URI as the Authorized redirect
# URI in the Google Cloud OAuth client, or connect fails with redirect_uri_mismatch.
# webmasters.readonly = read-only GSC. openid + userinfo.email let the gateway
# capture the account's address so multiple connected accounts stay distinct.
ext.oauth(
    "google",
    collection="gsc_accounts",
    scopes=[
        "https://www.googleapis.com/auth/webmasters.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
)

# ── App-scope secrets: ONE developer-owned Google OAuth Client for all users.
# Set google_client_id / google_client_secret from the Google Cloud OAuth client
# (Dev Portal -> secrets, or the IMPERAL_APPSECRET_* env fallback). The
# extension needs them at RUNTIME to refresh access tokens (token_refresh.py) —
# not just at the gateway. scope="app" already makes these owner-only (only the
# developer can set them, end users never can) — write_mode is ignored for
# app-scope by the SDK, so we don't set it.
ext.secret(
    name="google_client_id",
    description="Google OAuth Client ID for Search Console (developer-owned; one OAuth app for all users).",
    required=True, scope="app",
    env_fallback="IMPERAL_APPSECRET_GSC_GOOGLE_CLIENT_ID", max_bytes=512,
)(lambda: None)
ext.secret(
    name="google_client_secret",
    description="Google OAuth Client Secret for Search Console (developer-owned).",
    required=True, scope="app",
    env_fallback="IMPERAL_APPSECRET_GSC_GOOGLE_CLIENT_SECRET", max_bytes=512,
)(lambda: None)


# ctx.cache — short-lived (platform-capped 5-300s) per-user cache so the
# sidebar site-list and workspace opportunities/top-queries panels don't
# re-hit googleapis.com Search Analytics on every render. See cache_helpers.py.
from cache_helpers import CachedGscPayload  # noqa: E402
ext.cache_model("gsc_payload")(CachedGscPayload)


@ext.health_check
async def health(ctx) -> dict:
    # App-level probe, no user context - ctx.store is per-user and raises here
    # (kernel I-HEALTH-CTX-HONEST). GSC has no backend microservice of its own
    # (per-user Google OAuth straight to Google REST API - see module docstring
    # above), so there is no documented liveness endpoint to probe via ctx.http
    # either. Static liveness only, same pattern as mail-client/file-reader.
    return {"status": "ok", "version": ext.version}


@ext.on_install
async def on_install(ctx):
    uid = ctx.user.imperal_id if ctx and hasattr(ctx, "user") and ctx.user else "system"
    log.info(f"gsc-connector installed for user {uid}")
