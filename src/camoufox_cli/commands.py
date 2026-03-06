"""Command implementations for the daemon."""

from __future__ import annotations

import base64
import json

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_ref(manager: BrowserManager, ref_str: str):
    """Resolve a ref string to a locator, or raise."""
    entry = manager.refs.resolve(ref_str)
    if entry is None:
        raise ValueError(f"Ref @{ref_str.lstrip('@')} not found. Run 'camoufox-cli snapshot' to refresh refs.")
    page = manager.get_page()
    if entry.name:
        locator = page.get_by_role(entry.role, name=entry.name, exact=True)  # type: ignore[arg-type]
    else:
        locator = page.get_by_role(entry.role)  # type: ignore[arg-type]
    return locator.nth(entry.nth)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def _cmd_open(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    url = params.get("url", "")
    if not url:
        return error_response(cmd_id, "Missing 'url' parameter")

    if not manager.is_running:
        manager.launch(headless=params.get("headless", True))

    page = manager.get_page()
    page.goto(url, wait_until="domcontentloaded")
    manager.push_history(page.url)
    return ok_response(cmd_id, {"url": page.url, "title": page.title()})


def _cmd_back(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    url = manager.go_back()
    if url is None:
        return error_response(cmd_id, "No previous page in history")
    page = manager.get_page()
    return ok_response(cmd_id, {"url": page.url, "title": page.title()})


def _cmd_forward(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    url = manager.go_forward()
    if url is None:
        return error_response(cmd_id, "No next page in history")
    page = manager.get_page()
    return ok_response(cmd_id, {"url": page.url, "title": page.title()})


def _cmd_reload(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    page = manager.get_page()
    page.goto(page.url, wait_until="domcontentloaded")
    return ok_response(cmd_id)


def _cmd_url(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    return ok_response(cmd_id, {"url": manager.get_page().url})


def _cmd_title(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    return ok_response(cmd_id, {"title": manager.get_page().title()})


def _cmd_close(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    manager.close()
    return ok_response(cmd_id, {"closed": True})


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def _cmd_snapshot(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    page = manager.get_page()
    interactive = params.get("interactive", False)
    selector = params.get("selector")

    target = page.locator(selector) if selector else page.locator("body")
    aria_text = target.aria_snapshot()
    annotated = manager.refs.build_from_snapshot(aria_text, interactive_only=interactive)
    return ok_response(cmd_id, {"snapshot": annotated})


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------

def _cmd_click(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")
    locator = _resolve_ref(manager, ref_str)
    page = manager.get_page()
    url_before = page.url

    # For <a> elements: navigate directly via page.goto() to avoid two Camoufox issues:
    # 1. Playwright's .click() times out when sticky headers/overlays intercept pointer events
    # 2. Camoufox ignores target="_blank" clicks (both .click() and el.click() silently fail)
    # For non-<a> elements: use el.click() to dispatch the click directly, avoiding
    # Playwright's actionability checks that timeout on overlapping elements.
    link_info = locator.evaluate("el => el.tagName === 'A' ? el.href : null")
    if link_info:
        page.goto(link_info, wait_until="domcontentloaded")
    else:
        locator.evaluate("el => el.click()")

    url_after = page.url
    if url_after != url_before:
        manager.push_history(url_after)
    return ok_response(cmd_id)


def _cmd_fill(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    text = params.get("text", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")
    _resolve_ref(manager, ref_str).fill(text)
    return ok_response(cmd_id)


def _cmd_type(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    text = params.get("text", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")
    _resolve_ref(manager, ref_str).press_sequentially(text)
    return ok_response(cmd_id)


def _cmd_select(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    value = params.get("value", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")
    _resolve_ref(manager, ref_str).select_option(label=value)
    return ok_response(cmd_id)


def _cmd_check(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")
    locator = _resolve_ref(manager, ref_str)
    if locator.is_checked():
        locator.uncheck()
    else:
        locator.check()
    return ok_response(cmd_id)


def _cmd_hover(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ref_str = params.get("ref", "")
    if not ref_str:
        return error_response(cmd_id, "Missing 'ref' parameter")
    _resolve_ref(manager, ref_str).hover()
    return ok_response(cmd_id)


def _cmd_press(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    key = params.get("key", "")
    if not key:
        return error_response(cmd_id, "Missing 'key' parameter")
    manager.get_page().keyboard.press(key)
    return ok_response(cmd_id)


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def _cmd_text(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    target = params.get("target", "")
    if not target:
        return error_response(cmd_id, "Missing 'target' parameter")

    if target.startswith("@"):
        text = _resolve_ref(manager, target).text_content() or ""
    else:
        text = manager.get_page().locator(target).text_content() or ""

    return ok_response(cmd_id, {"text": text})


def _cmd_eval(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    expression = params.get("expression", "")
    if not expression:
        return error_response(cmd_id, "Missing 'expression' parameter")
    result = manager.get_page().evaluate(expression)
    return ok_response(cmd_id, {"result": result})


def _cmd_screenshot(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    page = manager.get_page()
    path = params.get("path")
    full_page = params.get("full_page", False)

    if path:
        page.screenshot(path=path, full_page=full_page)
        return ok_response(cmd_id, {"path": path})
    else:
        buf = page.screenshot(full_page=full_page)
        b64 = base64.b64encode(buf).decode("ascii")
        return ok_response(cmd_id, {"base64": b64})


def _cmd_pdf(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    return error_response(
        cmd_id,
        "PDF export is not supported with Firefox/Camoufox. Use 'screenshot --full' instead.",
    )


# ---------------------------------------------------------------------------
# Scroll & Wait
# ---------------------------------------------------------------------------

def _cmd_scroll(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    direction = params.get("direction", "down")
    amount = int(params.get("amount", 500))

    if direction == "up":
        amount = -amount

    manager.get_page().evaluate(f"window.scrollBy(0, {amount})")
    return ok_response(cmd_id)


def _cmd_wait(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    page = manager.get_page()

    if "ms" in params:
        page.wait_for_timeout(int(params["ms"]))
    elif "ref" in params:
        _resolve_ref(manager, params["ref"]).wait_for()
    elif "selector" in params:
        page.wait_for_selector(params["selector"])
    elif "url" in params:
        page.wait_for_url(params["url"])
    else:
        return error_response(cmd_id, "wait requires ms, ref, selector, or url parameter")

    return ok_response(cmd_id)


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------

def _cmd_tabs(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    return ok_response(cmd_id, {"tabs": manager.get_tabs()})


def _cmd_switch(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    index = params.get("index")
    if index is None:
        return error_response(cmd_id, "Missing 'index' parameter")
    page = manager.switch_to_tab(int(index))
    return ok_response(cmd_id, {"url": page.url, "title": page.title()})


def _cmd_close_tab(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    manager.close_current_tab()
    page = manager.get_page()
    return ok_response(cmd_id, {"url": page.url, "title": page.title()})


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------

def _cmd_cookies(manager: BrowserManager, cmd_id: str, params: dict) -> dict:
    ctx = manager.get_context()
    op = params.get("op", "list")

    if op == "list":
        cookies = ctx.cookies()
        return ok_response(cmd_id, {"cookies": cookies})

    elif op == "export":
        path = params.get("path", "")
        if not path:
            return error_response(cmd_id, "Missing 'path' parameter for export")
        cookies = ctx.cookies()
        with open(path, "w") as f:
            json.dump(cookies, f, indent=2)
        return ok_response(cmd_id, {"path": path, "count": len(cookies)})

    elif op == "import":
        path = params.get("path", "")
        if not path:
            return error_response(cmd_id, "Missing 'path' parameter for import")
        with open(path) as f:
            cookies = json.load(f)
        ctx.add_cookies(cookies)
        return ok_response(cmd_id, {"count": len(cookies)})

    else:
        return error_response(cmd_id, f"Unknown cookies op: {op}")


# ---------------------------------------------------------------------------
# Handler dispatch table
# ---------------------------------------------------------------------------

_HANDLERS = {
    # Navigation
    "open": _cmd_open,
    "back": _cmd_back,
    "forward": _cmd_forward,
    "reload": _cmd_reload,
    "url": _cmd_url,
    "title": _cmd_title,
    "close": _cmd_close,
    # Snapshot
    "snapshot": _cmd_snapshot,
    # Interaction
    "click": _cmd_click,
    "fill": _cmd_fill,
    "type": _cmd_type,
    "select": _cmd_select,
    "check": _cmd_check,
    "hover": _cmd_hover,
    "press": _cmd_press,
    # Data extraction
    "text": _cmd_text,
    "eval": _cmd_eval,
    "screenshot": _cmd_screenshot,
    "pdf": _cmd_pdf,
    # Scroll & Wait
    "scroll": _cmd_scroll,
    "wait": _cmd_wait,
    # Tab management
    "tabs": _cmd_tabs,
    "switch": _cmd_switch,
    "close-tab": _cmd_close_tab,
    # Cookies
    "cookies": _cmd_cookies,
}
