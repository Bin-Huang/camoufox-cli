"""Browser manager: launches and manages Camoufox instance."""

from __future__ import annotations

from camoufox.sync_api import Camoufox
from playwright.sync_api import Page

from .refs import RefRegistry


class BrowserManager:
    def __init__(self):
        self._camoufox: Camoufox | None = None
        self._browser = None
        self._page: Page | None = None
        self.refs = RefRegistry()
        self._headless: bool = True

    def launch(self, headless: bool = True) -> None:
        if self._camoufox is not None:
            return
        self._headless = headless
        self._camoufox = Camoufox(headless=headless)
        self._browser = self._camoufox.__enter__()
        self._page = self._browser.new_page()

    def get_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched. Send 'open' command first.")
        return self._page

    def close(self) -> None:
        if self._camoufox is not None:
            try:
                self._camoufox.__exit__(None, None, None)
            except Exception:
                pass
            self._camoufox = None
            self._browser = None
            self._page = None

    @property
    def is_running(self) -> bool:
        return self._camoufox is not None
