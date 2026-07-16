"""Leaf constants for the GSC connector — NO imports of sibling modules.

Sitting at the root of the import graph, this breaks the
gsc_accounts -> gsc_api -> token_refresh -> gsc_accounts cycle that previously
forced a runtime-deferred `from gsc_api import gsc_userinfo` inside
gsc_accounts. That deferred import blew up with "No module named 'gsc_api'"
whenever it ran after main.py had removed the extension dir from sys.path
(the module wasn't on the path AND wasn't guaranteed cached at that instant).
With the constant here, every sibling import resolves at LOAD time (dir still
on sys.path) and nothing needs the path at runtime.
"""
from __future__ import annotations

ACCOUNTS_COLLECTION = "gsc_accounts"
