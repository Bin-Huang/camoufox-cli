"""Unix socket server for the camoufox-cli daemon."""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
import time

from .browser import BrowserManager
from .commands import execute
from .protocol import parse_command, serialize_response


class DaemonServer:
    def __init__(self, session: str = "default", headless: bool = True, timeout: int = 1800, persistent: str | None = None, proxy: str | None = None, geoip: bool = True, locale: str | None = None):
        self.session = session
        self.headless = headless
        self.timeout = timeout  # idle timeout in seconds
        self.socket_path = f"/tmp/camoufox-cli-{session}.sock"
        self.pid_path = f"/tmp/camoufox-cli-{session}.pid"
        self.manager = BrowserManager(persistent=persistent, proxy=proxy, geoip=geoip, locale=locale)
        self._server_socket: socket.socket | None = None
        self._last_activity = time.time()
        self._running = False

    def start(self) -> None:
        self._cleanup_stale()
        self._write_pid()
        self._running = True

        # Start idle timeout watchdog
        watchdog = threading.Thread(target=self._idle_watchdog, daemon=True)
        watchdog.start()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._server_socket.bind(self.socket_path)
            self._server_socket.listen(5)
            self._server_socket.settimeout(1.0)  # allow periodic checks

            while self._running:
                try:
                    conn, _ = self._server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                self._last_activity = time.time()
                try:
                    self._handle_connection(conn)
                except Exception as e:
                    print(f"[camoufox-cli] Connection error: {e}", file=sys.stderr)
                finally:
                    conn.close()
        finally:
            self._shutdown()

    def _handle_connection(self, conn: socket.socket) -> None:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        line = data.decode("utf-8").strip()
        if not line:
            return

        command = parse_command(line)

        # Pass headless preference to open commands
        if command.get("action") == "open":
            command.setdefault("params", {}).setdefault("headless", self.headless)

        response = execute(self.manager, command)
        conn.sendall(serialize_response(response))

        # If close command, shut down the daemon
        if command.get("action") == "close":
            self._running = False

    def _idle_watchdog(self) -> None:
        while self._running:
            time.sleep(10)
            if time.time() - self._last_activity > self.timeout:
                print(f"[camoufox-cli] Idle timeout ({self.timeout}s), shutting down", file=sys.stderr)
                self._running = False
                # Nudge the accept() loop
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self.socket_path)
                    s.close()
                except Exception:
                    pass
                break

    def _handle_signal(self, signum, frame):
        self._running = False

    def _shutdown(self) -> None:
        self.manager.close()
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        self._cleanup_files()

    def _cleanup_stale(self) -> None:
        """Remove stale socket file if no daemon is running."""
        if os.path.exists(self.socket_path):
            # Check if another daemon is using it
            if os.path.exists(self.pid_path):
                try:
                    with open(self.pid_path) as f:
                        pid = int(f.read().strip())
                    os.kill(pid, 0)
                    # Process exists — abort
                    print(f"[camoufox-cli] Daemon already running (pid {pid})", file=sys.stderr)
                    sys.exit(1)
                except (ProcessLookupError, PermissionError, ValueError):
                    pass  # stale pid or other user's process, clean up
            os.unlink(self.socket_path)

    def _write_pid(self) -> None:
        with open(self.pid_path, "w") as f:
            f.write(str(os.getpid()))

    def _cleanup_files(self) -> None:
        for path in (self.socket_path, self.pid_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
