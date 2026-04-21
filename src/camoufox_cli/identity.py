"""Persistent identity: freeze fingerprint/OS into a persistent dir.

When a user launches with ``--persistent <dir>``, a ``camoufox-cli.json`` file
is written on first launch capturing the generated fingerprint, OS, locale,
and derived timezone/geolocation. Subsequent launches reload it so the browser
reports the same device identity to every site.

Fingerprint/OS/canvas+font seeds are frozen for the lifetime of the identity.
User-controllable fields (locale; proxy-derived timezone/geolocation) are
updated to match the command line whenever it's explicitly passed — so the
stored identity always reflects the most recent intent.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import random
import sys
from pathlib import Path
from typing import Any


IDENTITY_FILENAME = "camoufox-cli.json"
IDENTITY_VERSION = 1


def _host_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _identity_path(persistent_dir: str) -> Path:
    return Path(persistent_dir) / IDENTITY_FILENAME


def load_or_create(
    persistent_dir: str,
    locale: str | None,
    proxy: str | None,
    geoip: bool,
) -> dict:
    """Return the identity dict for this persistent directory.

    On first launch, a fresh identity is generated and written:
      - fingerprint: browserforge, firefox, host OS
      - canvas/font seeds: random, stored so future launches reproduce them
      - timezone/geolocation: derived via GeoIP if proxy is set and geoip=True
      - locale: recorded if passed on this first launch, else null

    On subsequent launches, ``<persistent_dir>/camoufox-cli.json`` is loaded.
    Fields the user explicitly passes on the command line overwrite the
    stored values (``--locale``; ``--proxy`` + geoip re-derives timezone /
    geolocation). Fingerprint, OS, and canvas/font seeds are never touched
    after first launch.
    """
    path = _identity_path(persistent_dir)
    if path.exists():
        identity = json.loads(path.read_text())
        if _apply_cli_overrides(identity, locale, proxy, geoip):
            path.write_text(json.dumps(identity, indent=2, ensure_ascii=False))
        return identity

    from browserforge.fingerprints import FingerprintGenerator

    os_ = _host_os()
    fp = FingerprintGenerator(browser="firefox", os=os_).generate()

    config: dict[str, Any] = {
        "canvas:aaOffset": random.randint(-50, 50),
        "canvas:aaCapOffset": bool(random.randint(0, 1)),
        "fonts:spacing_seed": random.randint(0, 2**32 - 1),
    }

    if proxy and geoip:
        _merge_geo(config, _geolocate_proxy(proxy))

    identity = {
        "version": IDENTITY_VERSION,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "os": os_,
        "locale": locale,
        "fingerprint": dataclasses.asdict(fp),
        "config": config,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity, indent=2, ensure_ascii=False))
    return identity


def _apply_cli_overrides(
    identity: dict,
    locale: str | None,
    proxy: str | None,
    geoip: bool,
) -> bool:
    """Mutate identity with CLI-passed values. Return True if anything changed."""
    changed = False

    if locale is not None and identity.get("locale") != locale:
        identity["locale"] = locale
        changed = True

    if proxy and geoip:
        config = identity.setdefault("config", {})
        derived = _geolocate_proxy(proxy)
        if derived and _merge_geo(config, derived):
            changed = True

    return changed


def _merge_geo(config: dict, derived: dict | None) -> bool:
    """Merge proxy-derived geo into config. Return True if anything changed."""
    if not derived:
        return False
    changed = False
    tz = derived.get("timezone")
    if tz and config.get("timezone") != tz:
        config["timezone"] = tz
        changed = True
    lat = derived.get("latitude")
    lon = derived.get("longitude")
    if lat is not None and lon is not None:
        if config.get("geolocation:latitude") != lat:
            config["geolocation:latitude"] = lat
            changed = True
        if config.get("geolocation:longitude") != lon:
            config["geolocation:longitude"] = lon
            changed = True
        acc = derived.get("accuracy")
        if acc is not None and config.get("geolocation:accuracy") != acc:
            config["geolocation:accuracy"] = acc
            changed = True
    return changed


def to_launch_kwargs(identity: dict) -> dict:
    """Translate identity dict into kwargs for Camoufox(**kwargs).

    Returns fingerprint/os/config (always) and locale (when set). Does NOT
    set persistent_context/user_data_dir — the caller handles those.
    """
    from browserforge.fingerprints import Fingerprint

    fp = _rebuild_dataclass(Fingerprint, identity["fingerprint"])
    kwargs: dict[str, Any] = {
        "fingerprint": fp,
        "os": identity["os"],
        "config": dict(identity.get("config") or {}),
    }

    stored_locale = identity.get("locale")
    if stored_locale:
        parts = [s.strip() for s in stored_locale.split(",") if s.strip()]
        if parts:
            kwargs["locale"] = parts if len(parts) > 1 else parts[0]

    return kwargs


def _rebuild_dataclass(cls, value):
    """Reconstruct a nested dataclass tree from a plain dict."""
    if value is None:
        return None
    if isinstance(cls, type) and dataclasses.is_dataclass(cls) and isinstance(value, dict):
        kwargs = {}
        for f in dataclasses.fields(cls):
            kwargs[f.name] = _rebuild_dataclass(f.type, value.get(f.name))
        return cls(**kwargs)
    return value


def _geolocate_proxy(proxy_url: str) -> dict | None:
    """Return {timezone, latitude, longitude, accuracy?} from the proxy's
    public IP, or None if anything fails."""
    try:
        from camoufox.ip import public_ip, valid_ipv4, valid_ipv6
        from camoufox.locale import get_geolocation
    except Exception:
        return None

    try:
        ip = public_ip(_proxy_url_with_auth(proxy_url))
        if not (valid_ipv4(ip) or valid_ipv6(ip)):
            return None
        geo = get_geolocation(ip)
        out: dict[str, Any] = {
            "timezone": geo.timezone,
            "latitude": geo.latitude,
            "longitude": geo.longitude,
        }
        if geo.accuracy:
            out["accuracy"] = geo.accuracy
        return out
    except Exception:
        return None


def _proxy_url_with_auth(proxy_url: str) -> str:
    """Rebuild proxy URL as scheme://user:pass@host:port for public_ip()."""
    from urllib.parse import urlparse

    from .proxy import parse_proxy_settings

    settings = parse_proxy_settings(proxy_url)
    parsed = urlparse(settings["server"])
    if "username" in settings:
        return f"{parsed.scheme}://{settings['username']}:{settings.get('password', '')}@{parsed.netloc}"
    return settings["server"]
