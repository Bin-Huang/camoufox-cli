"""Optional config file support.

A JSON file at ``~/.camoufox-cli/config.json`` (override with the
``CAMOUFOX_CLI_CONFIG`` env var) supplies default values for daemon-launch
flags, so common settings (proxy, locale, persistent…) don't have to be
repeated on every invocation.

Precedence: command-line flag > config ``sessions.<name>`` block >
config ``default`` block > built-in default.

Only flags that affect daemon launch are honored. ``session`` itself is never
read from config — it selects which block to apply, so it can only come from
the command line. Per-command flags (``--full``, ``-i``, …) are never read.

The config only takes effect when a session's daemon first launches; an
already-running daemon is reused as-is (see ``ensure_daemon``).
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any


CONFIG_PATH = os.environ.get("CAMOUFOX_CLI_CONFIG") or os.path.expanduser(
    "~/.camoufox-cli/config.json"
)

# Flags a config file may set, grouped by the value type each one expects.
# "session" is intentionally absent — it selects which block to apply, so it
# must come from the command line.
_BOOL_KEYS = {"headed", "geoip", "json"}
_STR_KEYS = {"proxy", "locale"}
_ALLOWED_KEYS = _BOOL_KEYS | _STR_KEYS | {"timeout", "persistent"}


def load_defaults(session: str) -> dict[str, Any]:
    """Return config-derived flag defaults for ``session``.

    Merges the top-level ``default`` block with the ``sessions.<session>``
    block (the latter wins). Returns ``{}`` when the file is absent or
    malformed — a broken config never blocks a command, it is only ignored
    with a warning on stderr.
    """
    path = CONFIG_PATH
    if not os.path.exists(path):
        return {}

    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[camoufox-cli] Ignoring config {path}: {e}", file=sys.stderr)
        return {}

    if not isinstance(raw, dict):
        print(f"[camoufox-cli] Ignoring config {path}: top level must be a JSON object", file=sys.stderr)
        return {}

    merged: dict[str, Any] = {}
    merged.update(_clean(raw.get("default"), path))

    sessions = raw.get("sessions")
    if isinstance(sessions, dict):
        merged.update(_clean(sessions.get(session), path))
    elif sessions is not None:
        print(f"[camoufox-cli] Ignoring config {path}: \"sessions\" must be an object", file=sys.stderr)

    return _normalize(merged)


def _clean(block: Any, path: str) -> dict[str, Any]:
    """Keep only allowed keys from a block, warning on anything else."""
    if block is None:
        return {}
    if not isinstance(block, dict):
        print(f"[camoufox-cli] Ignoring config {path}: blocks must be objects", file=sys.stderr)
        return {}
    out: dict[str, Any] = {}
    for key, value in block.items():
        if key in _ALLOWED_KEYS:
            out[key] = value
        elif key == "session":
            print("[camoufox-cli] Ignoring \"session\" in config — set it with --session on the command line", file=sys.stderr)
        else:
            print(f"[camoufox-cli] Ignoring unknown config key: {key}", file=sys.stderr)
    return out


def _normalize(flags: dict[str, Any]) -> dict[str, Any]:
    """Validate/coerce each config value to the type its flag expects.

    A value of the wrong type is dropped with a warning rather than passed
    through, so a malformed config is always ignored, never fatal: a non-string
    proxy/locale/persistent would crash subprocess launch, a non-numeric timeout
    would fail silently, and a non-bool toggle (e.g. the string "false") would
    be silently truthy.
    """
    out: dict[str, Any] = {}
    for key, value in flags.items():
        ok, coerced = _coerce(key, value)
        if ok:
            out[key] = coerced
        else:
            print(f"[camoufox-cli] Ignoring invalid {key} in config: {value!r}", file=sys.stderr)
    return out


def _coerce(key: str, value: Any) -> tuple[bool, Any]:
    """Return ``(True, normalized)`` if value fits the flag, else ``(False, None)``."""
    if key in _BOOL_KEYS:
        return (isinstance(value, bool), value)
    if key in _STR_KEYS:
        # null is accepted as "unset" (falls back to the built-in default).
        return (value is None or isinstance(value, str), value)
    if key == "timeout":
        # bool is an int subclass — exclude it; require a finite number.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return (False, None)
        return (True, int(value))
    if key == "persistent":
        # true -> "" (default profile path, resolved in main); false -> None
        # (disabled); null/string kept as-is; anything else invalid.
        if isinstance(value, bool):
            return (True, "" if value else None)
        return (value is None or isinstance(value, str), value)
    return (True, value)  # unreachable: _clean already filtered to known keys
