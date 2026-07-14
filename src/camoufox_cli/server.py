"""Unix socket server for the camoufox-cli daemon."""

from __future__ import annotations

import fcntl
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
        self.lock_path = f"/tmp/camoufox-cli-{session}.lock"
        self.manager = BrowserManager(persistent=persistent, proxy=proxy, geoip=geoip, locale=locale)
        self._server_socket: socket.socket | None = None
        self._lock_fd: int | None = None
        self._last_activity = time.time()
        self._running = False
        self._bound = False

    def start(self) -> None:
        self._claim_pid()
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
            self._bound = True
            # A large backlog matters under the --tab model: many agents connect
            # concurrently while this single-threaded daemon handles one command
            # at a time. With a small backlog the kernel refuses the overflow
            # connects, and the client mistakes that for a dead daemon and
            # deletes the live socket. A deep backlog lets connects queue (the
            # kernel accepts them) instead of being refused.
            self._server_socket.listen(socket.SOMAXCONN)
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

        # A close releases the caller's tab; the daemon exits only when that
        # was the last tab (the manager shut the browser down). Other agents'
        # tabs keep the daemon alive.
        if command.get("action") == "close" and not self.manager.is_running:
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

    def _claim_pid(self) -> None:
        """Claim the session via an exclusive advisory lock, or exit.

        Concurrent clients may each spawn a daemon for the same session. An
        ``flock`` on a per-session lock file is the mutex: exactly one daemon
        acquires it, and — crucially — the OS releases it automatically when the
        holder dies, so a hard-crashed (SIGKILL) daemon leaves no stale lock to
        race over. This sidesteps the TOCTOU that any pid-file read-then-unlink
        scheme has. The pid file is written (while holding the lock) purely for
        diagnostics / the "already running" message.

        Caveat: the two implementations use different mutexes (this flock vs the
        JS daemon's pid-file link), so running the Python and JavaScript daemons
        for the *same* session name concurrently is unsupported — pick one
        implementation per machine (they install the same `camoufox-cli`
        command, so normally only one is on PATH anyway).
        """
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Another live daemon holds the lock.
            try:
                with open(self.pid_path) as f:
                    pid = f.read().strip()
            except OSError:
                pid = "?"
            os.close(fd)
            print(f"[camoufox-cli] Daemon already running (pid {pid})", file=sys.stderr)
            sys.exit(1)
        # We hold the lock for the daemon's lifetime (released on close/exit).
        self._lock_fd = fd
        with open(self.pid_path, "w") as f:
            f.write(str(os.getpid()))
        # Clear any leftover socket from a dead daemon; we alone hold the lock.
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    def _cleanup_files(self) -> None:
        """Release the lock and remove the files this daemon owns. Holding the
        lock guarantees no other daemon owns the session, so this is safe."""
        if self._bound:
            try:
                os.unlink(self.socket_path)
            except FileNotFoundError:
                pass
        if self._lock_fd is not None:
            try:
                os.unlink(self.pid_path)
            except FileNotFoundError:
                pass
            try:
                os.close(self._lock_fd)  # releases the flock
            except OSError:
                pass
            self._lock_fd = None
