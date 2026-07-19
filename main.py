"""Google Search Console connector — entry point + hot-reload importer.

Purges our own modules from sys.modules on reload (and guards against
cross-extension name collisions), then imports the extension core and every
handler/skeleton/panel module so their decorators register.
"""
from __future__ import annotations

import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

_MODULES = (
    "app", "constants", "gsc_accounts", "token_refresh", "gsc_api",
    "params", "response_models", "cache_helpers",
    "handlers_connect", "handlers_sites", "handlers_analytics",
    "skeleton", "panels", "panels_workspace",
)
for _m in [k for k in sys.modules if k in _MODULES]:
    del sys.modules[_m]

from app import ext, chat  # noqa: E402, F401

import handlers_connect    # noqa: E402, F401
import handlers_sites      # noqa: E402, F401
import handlers_analytics  # noqa: E402, F401
import skeleton            # noqa: E402, F401
import panels              # noqa: E402, F401
import panels_workspace    # noqa: E402, F401

# Multiple extensions share one worker process and each inserts its own
# directory at sys.path[0] on load. Leaving it there after our imports are
# done means a LATER extension's plain `import accounts` (or any other
# same-named top-level module) can resolve to THIS extension's file instead
# of its own — this bit us for real: gsc-connector's own accounts.py got
# shadowed by a same-named file from another extension deployed afterward.
# Once our modules are cached in sys.modules under their bare names, the
# directory is no longer needed on sys.path — remove it so it can't leak
# into the next extension's load.
if _dir in sys.path:
    sys.path.remove(_dir)
