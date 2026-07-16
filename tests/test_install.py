"""Tests for resilient GitHub release discovery used by `install`."""

import requests

from camoufox_cli.install import _assets_via_web, iter_release_assets


RELEASES_PAGE_1 = (
    '<a href="/daijro/camoufox/releases/tag/v150.0.2-beta.25">x</a>'
    '<a href="/daijro/camoufox/releases/tag/v150.0.2-beta.25">dup</a>'
    '<a href="/daijro/camoufox/releases/tag/v135.0.1-beta.24">x</a>'
)
RELEASES_PAGE_2 = '<a href="/daijro/camoufox/releases/tag/v135.0.1-beta.23">x</a>'

EXPANDED_25 = '<a href="/daijro/camoufox/releases/download/v150.0.2-beta.25/camoufox-150.0.2-alpha.25-lin.x86_64.zip">a</a>'
EXPANDED_24 = (
    '<a href="/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-lin.x86_64.zip">a</a>'
    '<a href="/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-mac.arm64.zip">a</a>'
)
EXPANDED_23 = '<a href="/daijro/camoufox/releases/download/v135.0.1-beta.23/camoufox-135.0.1-beta.23-lin.x86_64.zip">a</a>'

# A prerelease section: its tag link is followed by the "Pre-release" badge
# (before the next release's tag), mirroring github.com's listing markup.
PRERELEASE_PAGE = (
    '<a href="/daijro/camoufox/releases/tag/v152.0.2-alpha">x</a>'
    '<span>Pre-release</span>'
    '<a href="/daijro/camoufox/releases/tag/v150.0.2-beta.25">x</a>'
)
PRERELEASE_ONLY_PAGE = (
    '<a href="/daijro/camoufox/releases/tag/v146-hardware">x</a>'
    '<span>Pre-release</span>'
)


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def route_requests(monkeypatch, routes):
    """Replace requests.get with a router keyed by URL prefix match."""
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        for prefix, resp in routes.items():
            if url.startswith(prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("camoufox_cli.install.requests.get", fake_get)
    return calls


WEB_ROUTES = {
    "https://github.com/daijro/camoufox/releases?page=1": FakeResponse(text=RELEASES_PAGE_1),
    "https://github.com/daijro/camoufox/releases?page=2": FakeResponse(text=RELEASES_PAGE_2),
    "https://github.com/daijro/camoufox/releases?page=": FakeResponse(text="<html>no releases</html>"),
    "https://github.com/daijro/camoufox/releases/expanded_assets/v150.0.2-beta.25": FakeResponse(text=EXPANDED_25),
    "https://github.com/daijro/camoufox/releases/expanded_assets/v135.0.1-beta.24": FakeResponse(text=EXPANDED_24),
    "https://github.com/daijro/camoufox/releases/expanded_assets/v135.0.1-beta.23": FakeResponse(text=EXPANDED_23),
}


class TestIterReleaseAssets:
    def test_api_success_flattens_releases(self, monkeypatch):
        a1 = {"name": "one.zip", "browser_download_url": "u1"}
        a2 = {"name": "two.zip", "browser_download_url": "u2"}
        a3 = {"name": "three.zip", "browser_download_url": "u3"}
        calls = route_requests(monkeypatch, {
            "https://api.github.com/repos/daijro/camoufox/releases": FakeResponse(
                json_data=[{"assets": [a1, a2]}, {"assets": [a3]}]
            ),
        })
        assert list(iter_release_assets("daijro/camoufox")) == [a1, a2, a3]
        assert len(calls) == 1

    def test_api_skips_prereleases_and_drafts(self, monkeypatch):
        """Prerelease/draft assets can be experimental or incomplete uploads
        (e.g. missing the browser binary) and must never be picked."""
        pre = {"name": "pre.zip", "browser_download_url": "u0"}
        draft = {"name": "draft.zip", "browser_download_url": "u1"}
        stable = {"name": "stable.zip", "browser_download_url": "u2"}
        route_requests(monkeypatch, {
            "https://api.github.com/repos/daijro/camoufox/releases": FakeResponse(
                json_data=[
                    {"prerelease": True, "assets": [pre]},
                    {"draft": True, "assets": [draft]},
                    {"assets": [stable]},
                ]
            ),
        })
        assert list(iter_release_assets("daijro/camoufox")) == [stable]

    def test_falls_back_to_web_on_rate_limit(self, monkeypatch, capsys):
        route_requests(monkeypatch, {
            "https://api.github.com": FakeResponse(status_code=403),
            **WEB_ROUTES,
        })
        assets = list(iter_release_assets("daijro/camoufox"))
        assert [a["name"] for a in assets] == [
            "camoufox-150.0.2-alpha.25-lin.x86_64.zip",
            "camoufox-135.0.1-beta.24-lin.x86_64.zip",
            "camoufox-135.0.1-beta.24-mac.arm64.zip",
            "camoufox-135.0.1-beta.23-lin.x86_64.zip",
        ]
        assert "falling back" in capsys.readouterr().err

    def test_falls_back_to_web_on_network_error(self, monkeypatch):
        route_requests(monkeypatch, {
            "https://api.github.com": requests.ConnectionError("no route"),
            **WEB_ROUTES,
        })
        assets = list(iter_release_assets("daijro/camoufox"))
        assert assets[0]["browser_download_url"].startswith(
            "https://github.com/daijro/camoufox/releases/download/"
        )


class TestAssetsViaWeb:
    def test_parses_names_and_urls(self, monkeypatch):
        route_requests(monkeypatch, WEB_ROUTES)
        assets = list(_assets_via_web("daijro/camoufox"))
        assert assets[0] == {
            "name": "camoufox-150.0.2-alpha.25-lin.x86_64.zip",
            "browser_download_url": "https://github.com/daijro/camoufox/releases/download/v150.0.2-beta.25/camoufox-150.0.2-alpha.25-lin.x86_64.zip",
        }
        assert len(assets) == 4

    def test_paginates_until_no_new_tags(self, monkeypatch):
        calls = route_requests(monkeypatch, WEB_ROUTES)
        assets = list(_assets_via_web("daijro/camoufox"))
        # Page 2's tag is reached, page 3 has no tags and ends the scan.
        assert assets[-1]["name"] == "camoufox-135.0.1-beta.23-lin.x86_64.zip"
        listing_calls = [u for u, _ in calls if "?page=" in u]
        assert listing_calls == [
            "https://github.com/daijro/camoufox/releases?page=1",
            "https://github.com/daijro/camoufox/releases?page=2",
            "https://github.com/daijro/camoufox/releases?page=3",
        ]

    def test_stops_when_pages_repeat(self, monkeypatch):
        # A listing that keeps returning the same tag must not loop forever.
        route_requests(monkeypatch, {
            "https://github.com/daijro/camoufox/releases?page=": FakeResponse(text=RELEASES_PAGE_2),
            "https://github.com/daijro/camoufox/releases/expanded_assets/v135.0.1-beta.23": FakeResponse(text=EXPANDED_23),
        })
        assets = list(_assets_via_web("daijro/camoufox"))
        assert [a["name"] for a in assets] == ["camoufox-135.0.1-beta.23-lin.x86_64.zip"]

    def test_lazy_stops_requesting_on_first_match(self, monkeypatch):
        calls = route_requests(monkeypatch, WEB_ROUTES)
        first = next(iter(_assets_via_web("daijro/camoufox")))
        assert first["name"] == "camoufox-150.0.2-alpha.25-lin.x86_64.zip"
        # Only the first listing page and the first release page were fetched.
        assert len(calls) == 2

    def test_skips_prerelease_sections(self, monkeypatch):
        calls = route_requests(monkeypatch, {
            "https://github.com/daijro/camoufox/releases?page=1": FakeResponse(text=PRERELEASE_PAGE),
            "https://github.com/daijro/camoufox/releases?page=": FakeResponse(text="<html>no releases</html>"),
            "https://github.com/daijro/camoufox/releases/expanded_assets/v150.0.2-beta.25": FakeResponse(text=EXPANDED_25),
        })
        assets = list(_assets_via_web("daijro/camoufox"))
        assert [a["name"] for a in assets] == ["camoufox-150.0.2-alpha.25-lin.x86_64.zip"]
        # The prerelease tag's assets page must not even be requested.
        assert not any("v152.0.2-alpha" in u for u, _ in calls)

    def test_prerelease_only_page_does_not_end_pagination(self, monkeypatch):
        route_requests(monkeypatch, {
            "https://github.com/daijro/camoufox/releases?page=1": FakeResponse(text=PRERELEASE_ONLY_PAGE),
            "https://github.com/daijro/camoufox/releases?page=2": FakeResponse(text=RELEASES_PAGE_2),
            "https://github.com/daijro/camoufox/releases?page=": FakeResponse(text="<html>no releases</html>"),
            "https://github.com/daijro/camoufox/releases/expanded_assets/v135.0.1-beta.23": FakeResponse(text=EXPANDED_23),
        })
        assets = list(_assets_via_web("daijro/camoufox"))
        # Page 1 held only a prerelease; the scan must reach page 2's stable release.
        assert [a["name"] for a in assets] == ["camoufox-135.0.1-beta.23-lin.x86_64.zip"]

    def test_skips_unavailable_release_pages(self, monkeypatch):
        route_requests(monkeypatch, {
            **WEB_ROUTES,
            "https://github.com/daijro/camoufox/releases/expanded_assets/v150.0.2-beta.25": FakeResponse(status_code=404),
        })
        assets = list(_assets_via_web("daijro/camoufox"))
        assert [a["name"] for a in assets] == [
            "camoufox-135.0.1-beta.24-lin.x86_64.zip",
            "camoufox-135.0.1-beta.24-mac.arm64.zip",
            "camoufox-135.0.1-beta.23-lin.x86_64.zip",
        ]
