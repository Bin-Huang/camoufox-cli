"""End-to-end tests exercising daemon server + socket protocol + real browser."""

import json
import os
import signal
import socket
import threading
import time
from unittest.mock import patch

import pytest

from camoufox_cli.server import DaemonServer

FIXTURE_URL = "file://" + os.path.join(os.path.dirname(__file__), "fixture.html")
TEST_SESSION = f"e2e-test-{os.getpid()}-{int(time.time())}"
SOCK_PATH = f"/tmp/camoufox-cli-{TEST_SESSION}.sock"
PID_PATH = f"/tmp/camoufox-cli-{TEST_SESSION}.pid"


def send_command(sock_path: str, cmd: dict) -> dict:
    """Send a JSON command over Unix socket and return parsed response."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    s.sendall((json.dumps(cmd) + "\n").encode())
    data = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    s.close()
    return json.loads(data.decode().strip())


def wait_for_socket(path: str, timeout: float = 10.0) -> None:
    """Wait until socket file appears."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path):
            return
        time.sleep(0.1)
    raise TimeoutError(f"Socket {path} not found after {timeout}s")


def _start_daemon_thread(server):
    """Start DaemonServer in a thread, skipping signal handlers (main-thread only)."""
    with patch.object(signal, "signal"):
        server.start()


@pytest.fixture(scope="module")
def daemon():
    """Start a DaemonServer in a background thread for all e2e tests."""
    server = DaemonServer(session=TEST_SESSION, headless=True, timeout=300)
    thread = threading.Thread(target=_start_daemon_thread, args=(server,), daemon=True)
    thread.start()
    wait_for_socket(SOCK_PATH)

    # Open fixture page
    resp = send_command(SOCK_PATH, {
        "id": "setup", "action": "open",
        "params": {"url": FIXTURE_URL},
    })
    assert resp["success"] is True

    yield SOCK_PATH

    # Shut down daemon
    try:
        send_command(SOCK_PATH, {"id": "teardown", "action": "close", "params": {}})
    except Exception:
        pass
    thread.join(timeout=10)


def cmd(sock_path: str, action: str, params=None, id: str = "r1") -> dict:
    """Shorthand for send_command."""
    return send_command(sock_path, {"id": id, "action": action, "params": params or {}})


def find_ref(snapshot_text: str, role: str) -> str:
    """Extract first ref for a given role from snapshot text."""
    for line in snapshot_text.split("\n"):
        if f"- {role}" in line and "[ref=" in line:
            start = line.index("[ref=") + 5
            end = line.index("]", start)
            return "@" + line[start:end]
    raise ValueError(f"No ref found for role '{role}' in snapshot")


@pytest.mark.integration
class TestE2E:
    """E2E tests: daemon server + Unix socket + real browser."""

    def test_open_returns_url_and_title(self, daemon):
        resp = cmd(daemon, "url")
        assert resp["success"] is True
        assert "fixture.html" in resp["data"]["url"]

        resp = cmd(daemon, "title")
        assert resp["success"] is True
        assert resp["data"]["title"] == "Test Fixture"

    def test_snapshot_has_refs(self, daemon):
        resp = cmd(daemon, "snapshot")
        assert resp["success"] is True
        assert "[ref=" in resp["data"]["snapshot"]

    def test_fill_textbox(self, daemon):
        resp = cmd(daemon, "snapshot")
        ref = find_ref(resp["data"]["snapshot"], "textbox")

        resp = cmd(daemon, "fill", {"ref": ref, "text": "E2E-Alice"})
        assert resp["success"] is True

        resp = cmd(daemon, "eval", {"expression": "document.getElementById('name').value"})
        assert resp["data"]["result"] == "E2E-Alice"

    def test_click_button(self, daemon):
        resp = cmd(daemon, "snapshot")
        ref = find_ref(resp["data"]["snapshot"], "button \"Submit\"")

        resp = cmd(daemon, "click", {"ref": ref})
        assert resp["success"] is True

        resp = cmd(daemon, "eval", {"expression": "document.getElementById('output').textContent"})
        assert resp["data"]["result"] == "clicked"

    def test_upload_file(self, daemon, tmp_path):
        resp = cmd(daemon, "snapshot")
        # File input is recognized as a button by aria-snapshot
        ref = find_ref(resp["data"]["snapshot"], "button \"File\"")

        # Create a dummy file to upload
        file_path = str(tmp_path / "test-upload.txt")
        with open(file_path, "w") as f:
            f.write("test content")

        resp = cmd(daemon, "upload", {"ref": ref, "files": [file_path]})
        assert resp["success"] is True

        resp = cmd(daemon, "eval", {"expression": "document.getElementById('output').textContent"})
        # The fixture updates #output to 'uploaded:' + name
        assert resp["data"]["result"] == "uploaded:test-upload.txt"

    def test_select_dropdown(self, daemon):
        resp = cmd(daemon, "snapshot")
        ref = find_ref(resp["data"]["snapshot"], "combobox")

        resp = cmd(daemon, "select", {"ref": ref, "value": "Green"})
        assert resp["success"] is True

        resp = cmd(daemon, "eval", {"expression": "document.getElementById('color').value"})
        assert resp["data"]["result"] == "green"

    def test_check_uncheck(self, daemon):
        resp = cmd(daemon, "snapshot")
        ref = find_ref(resp["data"]["snapshot"], "checkbox")

        # Check
        resp = cmd(daemon, "check", {"ref": ref})
        assert resp["success"] is True
        resp = cmd(daemon, "eval", {"expression": "document.getElementById('agree').checked"})
        assert resp["data"]["result"] is True

        # Uncheck
        resp = cmd(daemon, "check", {"ref": ref})
        assert resp["success"] is True
        resp = cmd(daemon, "eval", {"expression": "document.getElementById('agree').checked"})
        assert resp["data"]["result"] is False

    def test_scroll(self, daemon):
        resp = cmd(daemon, "scroll", {"direction": "down", "amount": 100})
        assert resp["success"] is True

    def test_wait_ms(self, daemon):
        resp = cmd(daemon, "wait", {"ms": 50})
        assert resp["success"] is True

    def test_press_key(self, daemon):
        # Take snapshot and focus textbox first
        resp = cmd(daemon, "snapshot")
        ref = find_ref(resp["data"]["snapshot"], "textbox")
        cmd(daemon, "click", {"ref": ref})

        resp = cmd(daemon, "press", {"key": "Tab"})
        assert resp["success"] is True

    def test_back_forward(self, daemon):
        # Navigate to a second page (use data: URI since about:blank may fail)
        resp = cmd(daemon, "open", {"url": "data:text/html,<h1>Page2</h1>"})
        assert resp["success"] is True

        # Go back to fixture
        resp = cmd(daemon, "back")
        assert resp["success"] is True
        assert "fixture.html" in resp["data"]["url"]

        # Go forward
        resp = cmd(daemon, "forward")
        assert resp["success"] is True

        # Navigate back to fixture for subsequent tests
        cmd(daemon, "open", {"url": FIXTURE_URL})

    def test_tabs(self, daemon):
        resp = cmd(daemon, "tabs")
        assert resp["success"] is True
        tabs = resp["data"]["tabs"]
        assert len(tabs) >= 1
        assert any(t["active"] for t in tabs)

    def test_cookies(self, daemon):
        resp = cmd(daemon, "cookies", {"op": "list"})
        assert resp["success"] is True
        assert "cookies" in resp["data"]

    def test_close_shuts_down_daemon(self):
        """Close command shuts down the daemon (run last, standalone)."""
        session = f"e2e-close-{os.getpid()}-{int(time.time())}"
        sock = f"/tmp/camoufox-cli-{session}.sock"
        server = DaemonServer(session=session, headless=True, timeout=60)
        thread = threading.Thread(target=_start_daemon_thread, args=(server,), daemon=True)
        thread.start()
        wait_for_socket(sock)

        resp = send_command(sock, {"id": "r1", "action": "close", "params": {}})
        assert resp["success"] is True

        thread.join(timeout=10)
        assert not os.path.exists(sock)
