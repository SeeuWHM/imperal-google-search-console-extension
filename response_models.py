"""Pydantic response models for GSC chat functions.

Every @chat.function(action_type="read") declares a data_model so the platform
validates return shapes and prevents naming drift (federal V23). Return raw
facts (ICNLI) — the narrator owns phrasing.
"""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class SiteRecord(BaseModel):
    site_url: str = ""
    permission_level: str = ""


class SiteList(BaseModel):
    sites: List[SiteRecord] = Field(default_factory=list)
    count: int = 0


class ConnectResult(BaseModel):
    auth_url: str = ""
    instruction: str = ""


class ConnectionStatus(BaseModel):
    connected: bool = False
    sites_count: int = 0
    accounts: List[str] = Field(default_factory=list)


class AccountRecord(BaseModel):
    email: str = ""
    is_active: bool = False


class AccountsList(BaseModel):
    accounts: List[AccountRecord] = Field(default_factory=list)
    count: int = 0


class AccountSwitched(BaseModel):
    active: str = ""


class AccountDisconnected(BaseModel):
    email: str = ""
    remaining: int = 0


class QueryRow(BaseModel):
    query: str = ""
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0        # percent (0-100)
    position: float = 0.0   # average position


class QueryList(BaseModel):
    site_url: str = ""
    rows: List[QueryRow] = Field(default_factory=list)
    count: int = 0


def build_query_list(site_url: str, rows: list[dict]) -> QueryList:
    qrows = [
        QueryRow(
            query=r.get("query", ""), clicks=r.get("clicks", 0),
            impressions=r.get("impressions", 0), ctr=r.get("ctr", 0.0),
            position=r.get("position", 0.0),
        )
        for r in rows
    ]
    return QueryList(site_url=site_url, rows=qrows, count=len(qrows))


def build_site_list(rows: list[dict]) -> SiteList:
    sites = [
        SiteRecord(site_url=r.get("site_url", ""), permission_level=r.get("permission_level", ""))
        for r in rows
    ]
    return SiteList(sites=sites, count=len(sites))


def build_accounts_list(emails: list[str], active_email: str) -> AccountsList:
    accs = [AccountRecord(email=e, is_active=(e == active_email)) for e in emails]
    return AccountsList(accounts=accs, count=len(accs))
