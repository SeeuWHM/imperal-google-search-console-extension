# Google Search Console Connector

[![Imperal SDK](https://img.shields.io/badge/imperal--sdk-5.9.12-blue)](https://pypi.org/project/imperal-sdk/)
[![Version](https://img.shields.io/badge/version-0.5.1-green)](https://github.com/SeeuWHM/imperal-google-search-console-extension/releases)
[![License](https://img.shields.io/badge/license-LGPL--2.1-orange)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Imperal%20Cloud-purple)](https://panel.imperal.io)

**Google Search Console extension for [Imperal Cloud](https://panel.imperal.io).**

Connect your own Google account and see your Search Console properties and their real Google Search performance — top queries, impressions, clicks, CTR and average position — straight from Google, no shared backend in the loop.

---

## What It Does

Talk to it naturally:

```
"connect google search console"
"show my top queries on webhostmost.com"
"which queries are almost ranking on page one"
"list my search console sites"
"switch to my other google account"
```

Or use the sidebar panel — every connected Google account is listed with the active one marked; click a site to open its opportunities and top queries in the center workspace.

---

## Capabilities

| Area | What it does |
|------|---------------|
| **Connect / accounts** | Start Google OAuth (read-only Search Console scope), check connection status, list connected accounts, switch the active one, disconnect one — several Google accounts can be connected at once |
| **Sites** | List the active account's verified Search Console properties (URL-prefix or domain properties) with permission level |
| **Search Analytics** | Top-performing queries (clicks, impressions, CTR %, average position) over a configurable look-back window (default 28 days) |
| **Striking distance** | "Almost ranking" queries — position 4–20 with ≥10 impressions — the best content/optimisation opportunities, sorted by impressions |

Field names (`query` / `clicks` / `impressions` / `position`) deliberately mirror the sibling **Bing Webmaster Connector**, so Webbee and the Article Writer extension see one consistent schema regardless of which search engine the data came from.

---

## Setup (for the end user)

1. Ask Webbee to **connect google search console** (or click **Connect Google Search Console** in the sidebar). This calls `connect_gsc`, which returns a Google OAuth authorisation URL opened in a popup window (`ui.Call`, not a plain browser tab — same behaviour as the Gmail/Google Drive connectors).
2. Sign in and grant **read-only Search Console access** (`webmasters.readonly`). The platform gateway exchanges the code for tokens and stores the account.
3. Call **list_sites** (or just ask) to see the verified properties that account can access.
4. Repeat step 1 to connect additional Google accounts — each is listed in the sidebar, click any inactive one to switch, or remove one with the account's Disconnect action.

Data is per-user: every connected account only ever sees its own Google Search Console properties.

---

## Architecture

```
imperal-google-search-console-extension/
├── main.py                # Entry point — sys.modules purge + import order, then drops the ext dir from sys.path
├── app.py                 # Extension + ChatExtension, ext.oauth("google"), app secrets, health check
├── constants.py            # ACCOUNTS_COLLECTION — leaf module, breaks an accounts↔api↔token import cycle
├── gsc_accounts.py         # Connected-account helpers: list/hydrate email/dedupe/active/lookup
├── gsc_api.py               # Thin REST wrappers over the Search Console API (sites, search analytics, userinfo)
├── token_refresh.py         # Refreshes a stored refresh_token into a fresh access token on demand
├── params.py / response_models.py  # Pydantic request/response models (federal V23 data_model contract)
├── skeleton.py              # gsc_config (ttl 300) + gsc_sites (ttl 600) — LLM context cache
├── handlers_connect.py      # connect_gsc, connection_status, list_accounts, switch_account, disconnect_account
├── handlers_sites.py        # list_sites
├── handlers_analytics.py    # top_queries, striking_distance (+ impl_ helpers reused by the panel, 0 tokens)
├── cache_helpers.py         # ctx.cache wrapper (cached_call) — panel reads share one TTL cache per account
├── panels.py                 # Left sidebar — account selector + verified sites (load-more)
├── panels_workspace.py       # Center panel — opportunities (striking-distance) + top queries (load-more), fetched concurrently via asyncio.gather
├── requirements.txt          # imperal-sdk>=5.9.9
├── tests/                    # pytest — accounts store, REST wrappers, every chat function (44 tests, no network)
└── imperal.json              # Extension manifest
```

No backend microservice — this extension calls Google's own Search Console REST API (`webmasters/v3`) directly via `ctx.http`, using each user's own refreshed OAuth access token.

---

## Function Reference

| Function | Type | Description |
|----------|------|-------------|
| `connect_gsc` | read | Returns a Google OAuth authorisation URL (read-only Search Console access) |
| `connection_status` | read | Whether a Google account is connected, how many, and the active account's site count |
| `list_accounts` | read | List connected Google accounts and which one is active |
| `switch_account` | write | Change the active Google account |
| `disconnect_account` | destructive | Disconnect a connected Google account (store record only — does not revoke the Google grant) |
| `list_sites` | read | List the active account's verified Search Console properties |
| `top_queries` | read | Best-performing search queries for a site over the last N days (default 28) |
| `striking_distance` | read | "Almost ranking" queries (position 4–20, ≥10 impressions) — content opportunities |

Two additional `@ext.skeleton` context providers (`gsc_config`, `gsc_sites`) keep connection status and the site list warm in the LLM context cache without a store round-trip on every turn.

---

## Development

```bash
python3 -m pytest tests/ -q          # 44 tests — accounts store, GSC REST wrappers (MockHTTP), every chat function
imperal build && imperal validate    # regenerate + lint imperal.json against the installed SDK
```

Both the sidebar (`gsc_sidebar`) and workspace (`gsc_workspace`) panels refresh automatically on
`account.connected` / `account.switched` / `account.disconnected` — no manual re-click needed after
connecting, switching or disconnecting a Google account. The workspace panel's two sections
(opportunities + top queries) fetch concurrently via `asyncio.gather`.

---

## Built with

- [imperal-sdk](https://github.com/imperalcloud/imperal-sdk) 5.9.12
- [Imperal Cloud](https://panel.imperal.io)
