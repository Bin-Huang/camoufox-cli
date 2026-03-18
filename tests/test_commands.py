"""Tests for command dispatch and execution logic."""

import os

import pytest

from camoufox_cli.commands import execute
from camoufox_cli.browser import BrowserManager

FIXTURE_URL = "file://" + os.path.join(os.path.dirname(__file__), "fixture.html")


class TestDispatch:
    """Test command dispatch without browser (error paths)."""

    def setup_method(self):
        self.manager = BrowserManager()

    def test_unknown_action(self):
        resp = execute(self.manager, {"id": "r1", "action": "nonexistent", "params": {}})
        assert resp["success"] is False
        assert "Unknown action" in resp["error"]

    def test_missing_action(self):
        resp = execute(self.manager, {"id": "r1", "params": {}})
        assert resp["success"] is False
        assert "Unknown action" in resp["error"]

    def test_preserves_command_id(self):
        resp = execute(self.manager, {"id": "test-123", "action": "nonexistent"})
        assert resp["id"] == "test-123"

    def test_default_id(self):
        resp = execute(self.manager, {"action": "nonexistent"})
        assert resp["id"] == "?"


class TestCommandValidation:
    """Test parameter validation without launching browser."""

    def setup_method(self):
        self.manager = BrowserManager()

    def test_open_missing_url(self):
        resp = execute(self.manager, {"id": "r1", "action": "open", "params": {}})
        assert resp["success"] is False
        assert "url" in resp["error"].lower()

    def test_click_missing_ref(self):
        resp = execute(self.manager, {"id": "r1", "action": "click", "params": {}})
        assert resp["success"] is False
        assert "ref" in resp["error"].lower()

    def test_fill_missing_ref(self):
        resp = execute(self.manager, {"id": "r1", "action": "fill", "params": {}})
        assert resp["success"] is False
        assert "ref" in resp["error"].lower()

    def test_type_missing_ref(self):
        resp = execute(self.manager, {"id": "r1", "action": "type", "params": {}})
        assert resp["success"] is False

    def test_select_missing_ref(self):
        resp = execute(self.manager, {"id": "r1", "action": "select", "params": {}})
        assert resp["success"] is False

    def test_check_missing_ref(self):
        resp = execute(self.manager, {"id": "r1", "action": "check", "params": {}})
        assert resp["success"] is False

    def test_hover_missing_ref(self):
        resp = execute(self.manager, {"id": "r1", "action": "hover", "params": {}})
        assert resp["success"] is False

    def test_press_missing_key(self):
        resp = execute(self.manager, {"id": "r1", "action": "press", "params": {}})
        assert resp["success"] is False
        assert "key" in resp["error"].lower()

    def test_text_missing_target(self):
        resp = execute(self.manager, {"id": "r1", "action": "text", "params": {}})
        assert resp["success"] is False

    def test_eval_missing_expression(self):
        resp = execute(self.manager, {"id": "r1", "action": "eval", "params": {}})
        assert resp["success"] is False

    def test_wait_missing_params(self):
        """wait with no params fails (either param validation or browser-not-launched)."""
        resp = execute(self.manager, {"id": "r1", "action": "wait", "params": {}})
        assert resp["success"] is False

    def test_switch_missing_index(self):
        resp = execute(self.manager, {"id": "r1", "action": "switch", "params": {}})
        assert resp["success"] is False

    def test_pdf_missing_path(self):
        resp = execute(self.manager, {"id": "r1", "action": "pdf", "params": {}})
        assert resp["success"] is False
        assert "path" in resp["error"].lower()

    def test_upload_missing_ref(self):
        resp = execute(self.manager, {"id": "r1", "action": "upload", "params": {"files": ["t.txt"]}})
        assert resp["success"] is False
        assert "ref" in resp["error"].lower()

    def test_upload_missing_files(self):
        resp = execute(self.manager, {"id": "r1", "action": "upload", "params": {"ref": "@e1"}})
        assert resp["success"] is False
        assert "files" in resp["error"].lower()


class TestBrowserNotLaunched:
    """Test commands that require browser when none is running."""

    def setup_method(self):
        self.manager = BrowserManager()

    def test_snapshot_fails(self):
        resp = execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        assert resp["success"] is False
        assert "not launched" in resp["error"].lower()

    def test_url_fails(self):
        resp = execute(self.manager, {"id": "r1", "action": "url", "params": {}})
        assert resp["success"] is False

    def test_title_fails(self):
        resp = execute(self.manager, {"id": "r1", "action": "title", "params": {}})
        assert resp["success"] is False

    def test_tabs_fails(self):
        resp = execute(self.manager, {"id": "r1", "action": "tabs", "params": {}})
        assert resp["success"] is False

    def test_scroll_fails(self):
        resp = execute(self.manager, {"id": "r1", "action": "scroll", "params": {"direction": "down"}})
        assert resp["success"] is False

    def test_close_succeeds(self):
        """Close on non-running browser should succeed silently."""
        resp = execute(self.manager, {"id": "r1", "action": "close", "params": {}})
        assert resp["success"] is True


class TestBrowserIntegration:
    """Integration tests that launch a real Camoufox browser.

    These tests are slower and require camoufox to be installed.
    Mark with 'integration' to allow skipping in CI.
    """

    @pytest.fixture(autouse=True)
    def setup_browser(self):
        self.manager = BrowserManager()
        yield
        self.manager.close()

    @pytest.mark.integration
    def test_open_and_navigate(self):
        resp = execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        assert resp["success"] is True
        assert "example.com" in resp["data"]["url"]
        assert resp["data"]["title"] != ""

    @pytest.mark.integration
    def test_url_after_open(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "url", "params": {}})
        assert resp["success"] is True
        assert "example.com" in resp["data"]["url"]

    @pytest.mark.integration
    def test_title_after_open(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "title", "params": {}})
        assert resp["success"] is True
        assert "Example" in resp["data"]["title"]

    @pytest.mark.integration
    def test_snapshot(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "snapshot", "params": {}})
        assert resp["success"] is True
        assert "[ref=e" in resp["data"]["snapshot"]

    @pytest.mark.integration
    def test_snapshot_interactive(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "snapshot", "params": {"interactive": True}})
        assert resp["success"] is True
        snapshot = resp["data"]["snapshot"]
        assert "link" in snapshot

    @pytest.mark.integration
    def test_click_link(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        # Take snapshot to build refs
        execute(self.manager, {"id": "r2", "action": "snapshot", "params": {"interactive": True}})
        # Find a link ref and click it
        resp = execute(self.manager, {"id": "r3", "action": "click", "params": {"ref": "@e1"}})
        assert resp["success"] is True

    @pytest.mark.integration
    def test_click_invalid_ref(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "click", "params": {"ref": "@e999"}})
        assert resp["success"] is False
        assert "not found" in resp["error"].lower()

    @pytest.mark.integration
    def test_eval(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "eval", "params": {"expression": "1 + 1"}})
        assert resp["success"] is True
        assert resp["data"]["result"] == 2

    @pytest.mark.integration
    def test_eval_document_title(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "eval", "params": {"expression": "document.title"}})
        assert resp["success"] is True
        assert "Example" in resp["data"]["result"]

    @pytest.mark.integration
    def test_screenshot_base64(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "screenshot", "params": {}})
        assert resp["success"] is True
        assert "base64" in resp["data"]
        assert len(resp["data"]["base64"]) > 100

    @pytest.mark.integration
    def test_screenshot_to_file(self, tmp_path):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        path = str(tmp_path / "test.png")
        resp = execute(self.manager, {"id": "r2", "action": "screenshot", "params": {"path": path}})
        assert resp["success"] is True
        import os
        assert os.path.exists(path)
        assert os.path.getsize(path) > 100

    @pytest.mark.integration
    def test_scroll(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "scroll", "params": {"direction": "down", "amount": 200}})
        assert resp["success"] is True

    @pytest.mark.integration
    def test_wait_ms(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "wait", "params": {"ms": 100}})
        assert resp["success"] is True

    @pytest.mark.integration
    def test_back_forward_history(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        execute(self.manager, {
            "id": "r2", "action": "open",
            "params": {"url": "https://www.iana.org/domains/reserved", "headless": True},
        })
        # Go back
        resp = execute(self.manager, {"id": "r3", "action": "back", "params": {}})
        assert resp["success"] is True
        assert "example.com" in resp["data"]["url"]
        # Go forward
        resp = execute(self.manager, {"id": "r4", "action": "forward", "params": {}})
        assert resp["success"] is True
        assert "iana.org" in resp["data"]["url"]

    @pytest.mark.integration
    def test_back_at_start(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "back", "params": {}})
        assert resp["success"] is False
        assert "no previous" in resp["error"].lower()

    @pytest.mark.integration
    def test_reload(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "reload", "params": {}})
        assert resp["success"] is True

    @pytest.mark.integration
    def test_tabs(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "tabs", "params": {}})
        assert resp["success"] is True
        tabs = resp["data"]["tabs"]
        assert len(tabs) >= 1
        assert tabs[0]["active"] is True

    @pytest.mark.integration
    def test_cookies_list(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "cookies", "params": {"op": "list"}})
        assert resp["success"] is True
        assert "cookies" in resp["data"]

    @pytest.mark.integration
    def test_close(self):
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r2", "action": "close", "params": {}})
        assert resp["success"] is True
        assert self.manager.is_running is False

    @pytest.mark.integration
    def test_reopen_after_close(self):
        """Test that browser can be relaunched after close."""
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        execute(self.manager, {"id": "r2", "action": "close", "params": {}})
        resp = execute(self.manager, {
            "id": "r3", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        assert resp["success"] is True

    @pytest.mark.integration
    def test_history_resets_after_close(self):
        """After close + reopen, back should fail (history cleared)."""
        execute(self.manager, {
            "id": "r1", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        execute(self.manager, {"id": "r2", "action": "close", "params": {}})
        execute(self.manager, {
            "id": "r3", "action": "open",
            "params": {"url": "https://example.com", "headless": True},
        })
        resp = execute(self.manager, {"id": "r4", "action": "back", "params": {}})
        assert resp["success"] is False


class TestFixtureIntegration:
    """Integration tests using local HTML fixture (no network needed)."""

    @pytest.fixture(autouse=True)
    def setup_browser(self):
        self.manager = BrowserManager()
        execute(self.manager, {
            "id": "r0", "action": "open",
            "params": {"url": FIXTURE_URL, "headless": True},
        })
        yield
        self.manager.close()

    @pytest.mark.integration
    def test_fill(self):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        # Find the textbox ref
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "textbox")
        resp = execute(self.manager, {
            "id": "r2", "action": "fill",
            "params": {"ref": f"@{entry.ref}", "text": "Alice"},
        })
        assert resp["success"] is True
        # Verify value was set
        resp = execute(self.manager, {
            "id": "r3", "action": "eval",
            "params": {"expression": "document.getElementById('name').value"},
        })
        assert resp["data"]["result"] == "Alice"

    @pytest.mark.integration
    def test_type(self):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "textbox")
        resp = execute(self.manager, {
            "id": "r2", "action": "type",
            "params": {"ref": f"@{entry.ref}", "text": "Bob"},
        })
        assert resp["success"] is True

    @pytest.mark.integration
    def test_select(self):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "combobox")
        resp = execute(self.manager, {
            "id": "r2", "action": "select",
            "params": {"ref": f"@{entry.ref}", "value": "Blue"},
        })
        assert resp["success"] is True
        resp = execute(self.manager, {
            "id": "r3", "action": "eval",
            "params": {"expression": "document.getElementById('color').value"},
        })
        assert resp["data"]["result"] == "blue"

    @pytest.mark.integration
    def test_check_toggle(self):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "checkbox")
        ref = f"@{entry.ref}"
        # Check
        resp = execute(self.manager, {"id": "r2", "action": "check", "params": {"ref": ref}})
        assert resp["success"] is True
        resp = execute(self.manager, {
            "id": "r3", "action": "eval",
            "params": {"expression": "document.getElementById('agree').checked"},
        })
        assert resp["data"]["result"] is True
        # Uncheck
        resp = execute(self.manager, {"id": "r4", "action": "check", "params": {"ref": ref}})
        assert resp["success"] is True
        resp = execute(self.manager, {
            "id": "r5", "action": "eval",
            "params": {"expression": "document.getElementById('agree').checked"},
        })
        assert resp["data"]["result"] is False

    @pytest.mark.integration
    def test_hover(self):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        # Pick the Submit button specifically to avoid picking up the File button
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "button" and e.name == "Submit")
        resp = execute(self.manager, {
            "id": "r2", "action": "hover",
            "params": {"ref": f"@{entry.ref}"},
        })
        assert resp["success"] is True


    @pytest.mark.integration
    def test_click_button(self):
        """Click a non-link button and verify side effect."""
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        # Pick the Submit button specifically
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "button" and e.name == "Submit")
        resp = execute(self.manager, {
            "id": "r2", "action": "click",
            "params": {"ref": f"@{entry.ref}"},
        })
        assert resp["success"] is True

        resp = execute(self.manager, {
            "id": "r3", "action": "eval",
            "params": {"expression": "document.getElementById('output').textContent"},
        })
        assert resp["data"]["result"] == "clicked"

    @pytest.mark.integration
    def test_upload(self, tmp_path):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        # File input is recognized as a button by aria-snapshot
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "button" and e.name == "File")
        
        # Create a dummy file to upload
        file_path = str(tmp_path / "test-upload.txt")
        with open(file_path, "w") as f:
            f.write("test content")

        resp = execute(self.manager, {
            "id": "r2", "action": "upload",
            "params": {"ref": f"@{entry.ref}", "files": [file_path]},
        })
        assert resp["success"] is True

        # Verify side effect in fixture (it updates #output)
        resp = execute(self.manager, {
            "id": "r3", "action": "eval",
            "params": {"expression": "document.getElementById('output').textContent"},
        })
        assert resp["data"]["result"] == "uploaded:test-upload.txt"

    @pytest.mark.integration
    def test_press(self):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "textbox")
        # Focus the textbox first
        execute(self.manager, {"id": "r2", "action": "click", "params": {"ref": f"@{entry.ref}"}})
        resp = execute(self.manager, {"id": "r3", "action": "press", "params": {"key": "Tab"}})
        assert resp["success"] is True

    @pytest.mark.integration
    def test_text_by_ref(self):
        execute(self.manager, {"id": "r1", "action": "snapshot", "params": {}})
        entry = next(e for e in self.manager.refs._entries.values() if e.role == "heading")
        resp = execute(self.manager, {
            "id": "r2", "action": "text",
            "params": {"target": f"@{entry.ref}"},
        })
        assert resp["success"] is True
        assert "Test Page" in resp["data"]["text"]

    @pytest.mark.integration
    def test_text_by_selector(self):
        resp = execute(self.manager, {
            "id": "r1", "action": "text",
            "params": {"target": "#output"},
        })
        assert resp["success"] is True
        assert resp["data"]["text"] == "ready"

    @pytest.mark.integration
    def test_cookies_export_import(self, tmp_path):
        cookie_file = str(tmp_path / "cookies.json")
        # Export
        resp = execute(self.manager, {
            "id": "r1", "action": "cookies",
            "params": {"op": "export", "path": cookie_file},
        })
        assert resp["success"] is True
        assert os.path.exists(cookie_file)
        # Import
        resp = execute(self.manager, {
            "id": "r2", "action": "cookies",
            "params": {"op": "import", "path": cookie_file},
        })
        assert resp["success"] is True

    @pytest.mark.integration
    def test_snapshot_scoped(self):
        resp = execute(self.manager, {
            "id": "r1", "action": "snapshot",
            "params": {"selector": "form"},
        })
        assert resp["success"] is True
        assert "textbox" in resp["data"]["snapshot"]
        # heading is outside form, should not appear
        assert "Test Page" not in resp["data"]["snapshot"]

    @pytest.mark.integration
    def test_wait_selector(self):
        resp = execute(self.manager, {
            "id": "r1", "action": "wait",
            "params": {"selector": "#output"},
        })
        assert resp["success"] is True

    @pytest.mark.integration
    def test_forward_at_end(self):
        resp = execute(self.manager, {"id": "r1", "action": "forward", "params": {}})
        assert resp["success"] is False
        assert "no next" in resp["error"].lower()
