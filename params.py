"""Pydantic param models for GSC chat functions."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EmptyParams(BaseModel):
    pass


class AccountParam(BaseModel):
    account: str = Field(
        default="",
        description="Connected Google account email (from list_accounts); defaults to the active one",
    )


class SiteParam(BaseModel):
    site_url: str = Field(
        ...,
        description="A GSC property from list_sites, e.g. 'https://example.com/' or 'sc-domain:example.com'",
    )


class QueryParams(BaseModel):
    site_url: str = Field(
        ...,
        description="A GSC property from list_sites, e.g. 'https://example.com/' or 'sc-domain:example.com'",
    )
    days: int = Field(default=28, ge=1, le=480, description="Look-back window in days (GSC keeps ~16 months)")
    limit: int = Field(default=25, ge=1, le=100, description="Max query rows to return")
