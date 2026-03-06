"""Browser manager: launches and manages Camoufox instance."""

from __future__ import annotations

from camoufox.sync_api import Camoufox
from playwright.sync_api import BrowserContext, Page

from .refs import RefRegistry


class BrowserManager:
    def __init__(self, persistent: str | None = None):
        self._camoufox: Camoufox | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self.refs = RefRegistry()
        self._headless: bool = True
        self._persistent = persistent
        # Camoufox spoofs history API for anti-fingerprinting,
        # so we track navigation history ourselves.
        self._history: list[str] = []
        self._history_index: int = -1

    def launch(self, headless: bool = True) -> None:
        if self._camoufox is not None:
            return
        self._headless = headless

        kwargs: dict = {"headless": headless}
        if self._persistent:
            kwargs["persistent_context"] = True
            kwargs["user_data_dir"] = self._persistent

        self._camoufox = Camoufox(**kwargs)
        result = self._camoufox.__enter__()

        if self._persistent:
            # persistent_context returns BrowserContext directly
            self._context = result
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
        else:
            # Normal mode: result is Browser, new_page() creates default context + page
            self._page = result.new_page()
            self._context = self._page.context

    def get_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched. Send 'open' command first.")
        return self._page

    def get_context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser not launched. Send 'open' command first.")
        return self._context

    def get_tabs(self) -> list[dict]:
        ctx = self.get_context()
        tabs = []
        for i, p in enumerate(ctx.pages):
            tabs.append({
                "index": i,
                "url": p.url,
                "title": p.title(),
                "active": p is self._page,
            })
        return tabs

    def switch_to_tab(self, index: int) -> Page:
        ctx = self.get_context()
        pages = ctx.pages
        if index < 0 or index >= len(pages):
            raise IndexError(f"Tab index {index} out of range (0-{len(pages) - 1})")
        self._page = pages[index]
        self._page.bring_to_front()
        return self._page

    def close_current_tab(self) -> None:
        ctx = self.get_context()
        pages = ctx.pages
        if len(pages) <= 1:
            raise RuntimeError("Cannot close the last tab. Use 'close' to shut down the browser.")
        current = self._page
        # Switch to another tab before closing
        idx = pages.index(current)
        new_idx = idx - 1 if idx > 0 else 1
        self._page = pages[new_idx]
        self._page.bring_to_front()
        current.close()

    def push_history(self, url: str) -> None:
        """Record a URL in our navigation history."""
        # Truncate forward history when navigating to a new page
        self._history = self._history[:self._history_index + 1]
        self._history.append(url)
        self._history_index = len(self._history) - 1

    def go_back(self) -> str | None:
        """Go back in history. Returns the URL or None if at start."""
        if self._history_index <= 0:
            return None
        self._history_index -= 1
        url = self._history[self._history_index]
        self.get_page().goto(url, wait_until="domcontentloaded")
        return url

    def go_forward(self) -> str | None:
        """Go forward in history. Returns the URL or None if at end."""
        if self._history_index >= len(self._history) - 1:
            return None
        self._history_index += 1
        url = self._history[self._history_index]
        self.get_page().goto(url, wait_until="domcontentloaded")
        return url

    def close(self) -> None:
        if self._camoufox is not None:
            try:
                self._camoufox.__exit__(None, None, None)
            except Exception:
                pass
            self._camoufox = None
            self._context = None
            self._page = None
            self._history.clear()
            self._history_index = -1

    @property
    def is_running(self) -> bool:
        return self._camoufox is not None
