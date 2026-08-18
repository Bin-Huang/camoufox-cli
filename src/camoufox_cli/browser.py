"""Browser manager: launches and manages Camoufox instance."""

from __future__ import annotations

import base64
import os

from camoufox.sync_api import Camoufox
from playwright.sync_api import BrowserContext, Page

from .identity import load_or_create, to_launch_kwargs
from .proxy import parse_proxy_settings
from .refs import RefRegistry


_MAX_HISTORY = 200


def _ensure_browser_installed() -> None:
    """Check that the Camoufox browser binary is installed, raise if not."""
    try:
        from camoufox.pkgman import get_path
        get_path("camoufox")
    except Exception:
        raise RuntimeError(
            "Browser not found. Run `camoufox-cli install` to download it."
        )


class TabState:
    """Per-tab state: page pointer, element refs, and navigation history.

    Every named tab shares the single browser context (same fingerprint,
    same cookies/login state) but keeps its own page and view state, so
    concurrent clients don't clobber each other.
    """

    def __init__(self):
        self.page: Page | None = None
        self.refs = RefRegistry()
        # Camoufox spoofs history API for anti-fingerprinting,
        # so we track navigation history ourselves.
        self.history: list[str] = []
        self.history_index: int = -1

    def push_history(self, url: str) -> None:
        # Truncate forward history when navigating to a new page
        self.history = self.history[:self.history_index + 1]
        self.history.append(url)
        # Cap history to avoid unbounded growth in long-lived daemons.
        if len(self.history) > _MAX_HISTORY:
            self.history = self.history[-_MAX_HISTORY:]
        self.history_index = len(self.history) - 1


class BrowserManager:
    def __init__(self, persistent: str | None = None, proxy: str | None = None, geoip: bool = True, locale: str | None = None):
        self._camoufox: Camoufox | None = None
        self._context: BrowserContext | None = None
        self._tabs: dict[str, TabState] = {}
        self._headless: bool = True
        self._persistent = persistent
        self._proxy = proxy
        self._geoip = geoip
        self._locale = locale

    def launch(self, headless: bool = True, tab: str = "default") -> None:
        if self._camoufox is not None:
            return
        self._headless = headless

        _ensure_browser_installed()

        if self._proxy and self._geoip:
            # Geoip resolution lazily downloads the GeoIP db via the
            # rate-limited GitHub API; fetch it through the resilient path first.
            from .install import ensure_mmdb

            ensure_mmdb()

        kwargs: dict = {"headless": headless}
        proxy_settings: dict | None = None
        if self._proxy:
            proxy_settings = parse_proxy_settings(self._proxy)
            kwargs["proxy"] = proxy_settings
            if self._geoip:
                kwargs["geoip"] = True

        if self._persistent:
            # Persistent identity: freeze fingerprint/OS on first launch; reload
            # it on subsequent launches. CLI-passed locale / proxy-derived geo
            # overwrite the stored values so the file tracks current intent.
            os.makedirs(self._persistent, exist_ok=True)
            identity = load_or_create(
                self._persistent,
                locale=self._locale,
                proxy=self._proxy,
                geoip=self._geoip,
            )
            kwargs.update(to_launch_kwargs(identity))
            kwargs["persistent_context"] = True
            kwargs["user_data_dir"] = self._persistent
        elif self._locale:
            # Non-persistent path: locale is a one-shot override, no identity file.
            locales = [s.strip() for s in self._locale.split(",") if s.strip()]
            if locales:
                kwargs["locale"] = locales if len(locales) > 1 else locales[0]

        # A failure partway through leaves _camoufox set but the context/page
        # missing; without this cleanup every later launch() would short-circuit
        # on `_camoufox is not None` and the daemon would be wedged forever.
        try:
            self._camoufox = Camoufox(**kwargs)
            result = self._camoufox.__enter__()

            if self._persistent:
                # persistent_context returns BrowserContext directly
                self._context = result
                pages = self._context.pages
                page = pages[0] if pages else self._context.new_page()
            else:
                # Normal mode: result is Browser. Create an explicit context so
                # more tabs can be added later — the implicit context made by
                # browser.new_page() refuses context.new_page().
                self._context = result.new_context()
                page = self._context.new_page()
            self.state(tab).page = page

            # Workaround: Playwright's Firefox (Juggler) fails proxy auth on HTTPS
            # CONNECT tunnels, raising NS_ERROR_PROXY_AUTHENTICATION_FAILED.
            # Inject Basic auth as an extra HTTP header like WebKit/Chromium do.
            if proxy_settings and proxy_settings.get("username"):
                creds = f"{proxy_settings['username']}:{proxy_settings.get('password', '')}"
                token = base64.b64encode(creds.encode()).decode()
                self._context.set_extra_http_headers(
                    {"Proxy-Authorization": f"Basic {token}"}
                )
        except Exception:
            # Roll back partial state so a later launch() can retry cleanly.
            self.close()
            raise

    def state(self, tab: str) -> TabState:
        """Get (lazily creating) the state record for a named tab."""
        st = self._tabs.get(tab)
        if st is None:
            st = TabState()
            self._tabs[tab] = st
        return st

    def get_page(self, tab: str = "default", create: bool = False) -> Page:
        """Get the tab's page.

        With ``create`` (navigation commands only) a missing/closed page is
        lazily (re)created in the shared context — a new tab gets its own page
        with the same fingerprint and cookies as every other tab. Without it,
        a command on a tab that never opened a page fails loudly instead of
        silently operating on a blank about:blank (which would also leak a
        stray page per misrouted/typo'd tab name).
        """
        ctx = self.get_context()
        st = self.state(tab)
        if st.page is None or st.page.is_closed():
            if not create:
                raise RuntimeError(f"Tab '{tab}' has no open page. Send 'open <url>' first.")
            st.page = ctx.new_page()
        return st.page

    def get_context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser not launched. Send 'open' command first.")
        return self._context

    def get_tabs(self, tab: str = "default") -> list[dict]:
        ctx = self.get_context()
        current = self._tabs.get(tab)
        owners: dict[Page, str] = {}
        for name, st in self._tabs.items():
            if st.page is not None:
                owners.setdefault(st.page, name)
        tabs = []
        for i, p in enumerate(ctx.pages):
            tabs.append({
                "index": i,
                "url": p.url,
                "title": p.title(),
                "active": current is not None and p is current.page,
                "tab": owners.get(p),
            })
        return tabs

    def switch_to_tab(self, tab: str, index: int) -> Page:
        ctx = self.get_context()
        pages = ctx.pages
        if index < 0 or index >= len(pages):
            raise IndexError(f"Tab index {index} out of range (0-{len(pages) - 1})")
        st = self.state(tab)
        st.page = pages[index]
        # The refs and history describe the previous page, not this one — reset
        # them so a stale @ref can't resolve against the newly-adopted page.
        st.refs = RefRegistry()
        st.history = []
        st.history_index = -1
        st.page.bring_to_front()
        return st.page

    def release_tab(self, tab: str) -> None:
        """Close the named tab; last one out shuts down the whole browser.

        This is the 'close' command. Every caller — solo or one of many
        concurrent agents — runs the same thing without knowing about the
        others: it closes only the caller's own page (never a neighbor's,
        which would hijack another agent's tab), and when no live tab
        remains the browser itself is closed. Idempotent: releasing a tab
        that has no open page is a no-op, not an error.
        """
        st = self._tabs.pop(tab, None)
        if st is not None and st.page is not None and not st.page.is_closed():
            try:
                st.page.close()
            except Exception:
                pass
        # Tabs (not context pages) are the refcount: pages nobody owns —
        # window.open popups, pages of misrouted tab names — must not keep
        # the browser alive after the last real tab leaves.
        for other in self._tabs.values():
            if other.page is not None and not other.page.is_closed():
                return
        self.close()

    def go_back(self, tab: str = "default") -> str | None:
        """Go back in the tab's history. Returns the URL or None if at start."""
        st = self.state(tab)
        if st.history_index <= 0:
            return None
        st.history_index -= 1
        url = st.history[st.history_index]
        self.get_page(tab, create=True).goto(url, wait_until="domcontentloaded")
        return url

    def go_forward(self, tab: str = "default") -> str | None:
        """Go forward in the tab's history. Returns the URL or None if at end."""
        st = self.state(tab)
        if st.history_index >= len(st.history) - 1:
            return None
        st.history_index += 1
        url = st.history[st.history_index]
        self.get_page(tab, create=True).goto(url, wait_until="domcontentloaded")
        return url

    def close(self) -> None:
        if self._camoufox is not None:
            try:
                self._camoufox.__exit__(None, None, None)
            except Exception:
                pass
            self._camoufox = None
            self._context = None
            self._tabs.clear()

    @property
    def is_running(self) -> bool:
        return self._camoufox is not None


class TabView:
    """BrowserManager scoped to one named tab.

    Command handlers work against this view, so each client's commands
    route to its own page/refs/history while sharing the browser context
    (fingerprint + cookies) with every other tab.
    """

    def __init__(self, manager: BrowserManager, tab: str):
        self._manager = manager
        self.tab = tab

    @property
    def refs(self) -> RefRegistry:
        return self._manager.state(self.tab).refs

    @property
    def is_running(self) -> bool:
        return self._manager.is_running

    def launch(self, headless: bool = True) -> None:
        self._manager.launch(headless=headless, tab=self.tab)

    def get_page(self, create: bool = False) -> Page:
        return self._manager.get_page(self.tab, create=create)

    def get_context(self) -> BrowserContext:
        return self._manager.get_context()

    def get_tabs(self) -> list[dict]:
        return self._manager.get_tabs(self.tab)

    def switch_to_tab(self, index: int) -> Page:
        return self._manager.switch_to_tab(self.tab, index)

    def push_history(self, url: str) -> None:
        self._manager.state(self.tab).push_history(url)

    def go_back(self) -> str | None:
        return self._manager.go_back(self.tab)

    def go_forward(self) -> str | None:
        return self._manager.go_forward(self.tab)

    def release(self) -> None:
        """Close this tab; the browser shuts down when the last tab leaves."""
        self._manager.release_tab(self.tab)

    def shutdown(self) -> None:
        """Force-close the whole browser regardless of other tabs (close --all)."""
        self._manager.close()
