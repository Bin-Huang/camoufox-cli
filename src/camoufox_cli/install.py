"""Browser installation with resilient GitHub release discovery.

Anonymous GitHub API requests are limited to 60/hour per IP, which makes
installs flaky on servers behind shared egress IPs (CI runners, cloud hosts).
Mitigations:

- If the API fails, release assets are discovered by paging through
  github.com release pages, which are not behind the API rate limit.
- The GeoIP database is downloaded from a fixed releases/latest/download URL
  (no API involved) at install time and before geoip launches, so upstream's
  lazy API-based download never triggers.
"""

from __future__ import annotations

import re
import sys
from itertools import count
from typing import Iterator
from urllib.parse import unquote

import requests

_HEADERS = {"User-Agent": "camoufox-cli"}
_MMDB_URL = "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb"


def _assets_via_api(repo: str) -> list[dict]:
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/releases",
        headers=_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    return [asset for release in resp.json() for asset in release["assets"]]


def _assets_via_web(repo: str) -> Iterator[dict]:
    """Discover release assets by paging through github.com release pages,
    newest release first. Lazy: stops requesting once the caller stops."""
    seen: set[str] = set()
    for page_num in count(1):
        listing = requests.get(
            f"https://github.com/{repo}/releases?page={page_num}",
            headers=_HEADERS,
            timeout=20,
        )
        listing.raise_for_status()
        tags = [
            tag
            for tag in dict.fromkeys(
                re.findall(rf'/{re.escape(repo)}/releases/tag/([^"<]+)', listing.text)
            )
            if tag not in seen
        ]
        if not tags:
            return
        seen.update(tags)
        for tag in tags:
            page = requests.get(
                f"https://github.com/{repo}/releases/expanded_assets/{tag}",
                headers=_HEADERS,
                timeout=20,
            )
            if page.status_code != 200:
                continue
            for path in re.findall(
                rf'href="(/{re.escape(repo)}/releases/download/[^"]+)"', page.text
            ):
                yield {
                    "name": unquote(path.rsplit("/", 1)[-1]),
                    "browser_download_url": f"https://github.com{path}",
                }


def iter_release_assets(repo: str) -> Iterator[dict]:
    """Yield all release assets of a repo, newest release first."""
    try:
        assets = _assets_via_api(repo)
    except requests.RequestException as e:
        print(
            f"[camoufox-cli] GitHub API failed ({e}), falling back to github.com pages...",
            file=sys.stderr,
        )
        yield from _assets_via_web(repo)
        return
    yield from assets


def ensure_mmdb() -> None:
    """Download the GeoIP database if missing, without hitting the GitHub API.

    Failures are non-fatal: upstream still lazily downloads on first use.
    """
    from camoufox.locale import ALLOW_GEOIP, MMDB_FILE
    from camoufox.pkgman import webdl

    if not ALLOW_GEOIP or MMDB_FILE.exists():
        return
    try:
        with open(MMDB_FILE, "wb") as f:
            webdl(_MMDB_URL, desc="Downloading GeoIP database", buffer=f)
        return
    except Exception:
        MMDB_FILE.unlink(missing_ok=True)
    try:
        from camoufox.locale import download_mmdb

        download_mmdb()  # upstream API-based path, as a last resort
    except Exception as e:
        MMDB_FILE.unlink(missing_ok=True)
        print(f"[camoufox-cli] GeoIP database download failed ({e}).", file=sys.stderr)


def install_browser() -> None:
    """Download and install the Camoufox browser and GeoIP database."""
    from camoufox.pkgman import CamoufoxFetcher

    class ResilientFetcher(CamoufoxFetcher):
        def get_asset(self):
            for asset in iter_release_assets(self.github_repo):
                if data := self.check_asset(asset):
                    return data
            self.missing_asset_error()

    ResilientFetcher().install()
    ensure_mmdb()
