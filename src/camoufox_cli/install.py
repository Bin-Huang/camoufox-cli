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
    # Skip prereleases/drafts like upstream's fetcher does: their assets can
    # be experimental or incomplete uploads (e.g. missing the browser binary)
    # and must never win over the newest stable release.
    return [
        asset
        for release in resp.json()
        if not (release.get("prerelease") or release.get("draft"))
        for asset in release["assets"]
    ]


def _stable_tags(listing_html: str, repo: str) -> list[str]:
    """Extract release tags from a listing page, skipping prereleases.

    The scrape path cannot see the API's ``prerelease`` flag; on the listing
    page a prerelease shows a "Pre-release" badge inside its section, i.e.
    between its tag link and the next release's tag link. Scan tag links and
    badges as one ordered stream and drop any tag followed by a badge.
    """
    token_re = re.compile(
        rf'/{re.escape(repo)}/releases/tag/([^"<]+)|(Pre-release)'
    )
    tags: list[str] = []
    prerelease: set[str] = set()
    current: str | None = None
    for m in token_re.finditer(listing_html):
        tag = m.group(1)
        if tag is not None:
            current = tag
            if tag not in tags:
                tags.append(tag)
        elif current is not None:
            prerelease.add(current)
    return [t for t in tags if t not in prerelease]


def _assets_via_web(repo: str) -> Iterator[dict]:
    """Discover release assets by paging through github.com release pages,
    newest stable release first. Lazy: stops requesting once the caller stops."""
    seen: set[str] = set()
    for page_num in count(1):
        listing = requests.get(
            f"https://github.com/{repo}/releases?page={page_num}",
            headers=_HEADERS,
            timeout=20,
        )
        listing.raise_for_status()
        # Pagination must advance on ANY new tag (a page holding only
        # prereleases is not the end of the listing), while assets are
        # fetched only for the stable ones.
        page_tags = dict.fromkeys(
            re.findall(rf'/{re.escape(repo)}/releases/tag/([^"<]+)', listing.text)
        )
        new_tags = [tag for tag in page_tags if tag not in seen]
        if not new_tags:
            return
        seen.update(new_tags)
        stable = set(_stable_tags(listing.text, repo))
        for tag in new_tags:
            if tag not in stable:
                continue
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


def _browser_present() -> bool:
    """True when the browser's launch executable is actually on disk."""
    from camoufox.exceptions import CamoufoxNotInstalled
    from camoufox.pkgman import launch_path

    try:
        launch_path()
        return True
    except (CamoufoxNotInstalled, FileNotFoundError):
        return False


def install_browser() -> None:
    """Download and install the Camoufox browser, GeoIP database and addons."""
    from camoufox.addons import DefaultAddons, maybe_download_addons
    from camoufox.pkgman import CamoufoxFetcher, installed_verstr, launch_path

    class ResilientFetcher(CamoufoxFetcher):
        def get_asset(self):
            for asset in iter_release_assets(self.github_repo):
                if data := self.check_asset(asset):
                    return data
            self.missing_asset_error()

    fetcher = ResilientFetcher()
    # Match the JS installer: skip the ~600MB download when version.json
    # already matches AND the binary is actually present. Without the
    # presence check a broken install (version file, no binary) would be
    # masked forever; without the version check every `install` re-downloads.
    try:
        installed = installed_verstr()
    except Exception:
        installed = None
    if installed == fetcher.verstr and _browser_present():
        print(f"[camoufox-cli] Camoufox v{installed} is already up to date.", file=sys.stderr)
    else:
        fetcher.install()
        # A broken release asset (e.g. one missing the browser binary) would
        # otherwise "install" successfully, write version.json, and mask the
        # failure forever. Fail loudly here instead of at the first `open`.
        launch_path()  # raises CamoufoxNotInstalled if the executable is absent

    ensure_mmdb()
    # Default UBO addon — same as `camoufox fetch`. Without this, first open
    # either downloads lazily or fails if an empty addons/ dir was left behind.
    maybe_download_addons(list(DefaultAddons))
