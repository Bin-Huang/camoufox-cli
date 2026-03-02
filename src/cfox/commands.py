"""Command implementations for the daemon."""

from __future__ import annotations

from .browser import BrowserManager
from .protocol import ok_response, error_response


def execute(manager: BrowserManager, command: dict) -> dict:
    """Dispatch and execute a command, return a response dict."""
    cmd_id = command.get("id", "?")
    action = command.get("action", "")
    params = command.get("params", {})

    try:
        handler = _HANDLERS.get(action)
        if handler is None:
            return error_response(cmd_id, f"Unknown action: {action}")
        return handler(manager, cmd_id, params)
    except Exception as e:
        return error_response(cmd_id, str(e))


def _cmd_open(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    url = params.get("url", "")
    if not url:
        return error_response(cmd_id, "Missing 'url' parameter")

    if not manager.is_running:
        manager.launch(headless=params.get("headless", True))

    page = manager.get_page()
    page.goto(url, wait_until="domcontentloaded")
    return ok_response(cmd_id, {"url": page.url, "title": page.title()})


def _cmd_snapshot(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    page = manager.get_page()
    interactive = params.get("interactive", False)

    aria_text = page.locator("body").aria_snapshot()
    annotated = manager.refs.build_from_snapshot(aria_text, interactive_only=interactive)
    return ok_response(cmd_id, {"snapshot": annotated})


def _cmd_click(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")

    entry = manager.refs.resolve(ref_str)
    if entry is None:
        return error_response(cmd_id, f"Ref @{ref_str.lstrip('@')} not found. Run 'cfox snapshot' to refresh refs.")

    page = manager.get_page()
    locator = page.get_by_role(entry.role, name=entry.name)
    if entry.nth > 0:
        locator = locator.nth(entry.nth)
    locator.click()
    return ok_response(cmd_id)


def _cmd_fill(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    text = params.get("text", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")

    entry = manager.refs.resolve(ref_str)
    if entry is None:
        return error_response(cmd_id, f"Ref @{ref_str.lstrip('@')} not found. Run 'cfox snapshot' to refresh refs.")

    page = manager.get_page()
    locator = page.get_by_role(entry.role, name=entry.name)
    if entry.nth > 0:
        locator = locator.nth(entry.nth)
    locator.fill(text)
    return ok_response(cmd_id)


def _cmd_close(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    manager.close()
    return ok_response(cmd_id, {"closed": True})


_HANDLERS = {
    "open": _cmd_open,
    "snapshot": _cmd_snapshot,
    "click": _cmd_click,
    "fill": _cmd_fill,
    "close": _cmd_close,
}
