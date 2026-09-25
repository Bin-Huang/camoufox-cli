"""Tests for daemon pid-file claiming (startup race hardening)."""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

from camoufox_cli import server as server_module
from camoufox_cli.server import DaemonServer


@pytest.fixture
def server():
    session = f"claim-test-{os.getpid()}-{time.monotonic_ns()}"
    srv = DaemonServer(session=session)
    yield srv
    if srv._lock_fd is not None:
        try:
            os.close(srv._lock_fd)
        except OSError:
            pass
    for path in (srv.pid_path, srv.socket_path, srv.lock_path):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


class TestClaimPid:
    def test_claims_empty(self, server):
        server._claim_pid()
        with open(server.pid_path) as f:
            assert f.read().strip() == str(os.getpid())

    def test_exits_when_alive_daemon_owns_pid(self, server):
        # Our own pid is alive, so a second claim must lose and exit.
        server._claim_pid()
        loser = DaemonServer(session=server.session)
        with pytest.raises(SystemExit):
            loser._claim_pid()
        # Loser must not have touched the winner's pid file.
        with open(server.pid_path) as f:
            assert f.read().strip() == str(os.getpid())

    def test_reclaims_stale_pid(self, server):
        with open(server.pid_path, "w") as f:
            f.write("999999999")  # not a real process
        server._claim_pid()
        with open(server.pid_path) as f:
            assert f.read().strip() == str(os.getpid())

    def test_concurrent_claims_single_winner_with_stale_pid(self, server):
        """With a stale pid file and many daemons racing, exactly one acquires
        the session lock and the pid file holds that winner. A read-then-unlink
        scheme could let two racers both 'win'; the flock cannot."""
        with open(server.pid_path, "w") as f:
            f.write("999999999")  # stale pid left by a crashed daemon

        # The winner holds the lock (sleeps) through the race window, mirroring a
        # real daemon that keeps running; losers hit LOCK_NB and exit at once.
        worker = (
            "import sys, os, time\n"
            "from camoufox_cli.server import DaemonServer\n"
            "srv = DaemonServer(session=sys.argv[1])\n"
            "srv._claim_pid()\n"                  # losers sys.exit(1) here
            "print(os.getpid(), flush=True)\n"    # only a winner reaches here
            "time.sleep(1.5)\n"
        )
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", worker, server.session],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
            for _ in range(12)
        ]
        winners = [out.strip() for p in procs for out in [p.communicate()[0]] if out.strip()]

        assert len(winners) == 1, f"expected exactly one winner, got {winners}"
        with open(server.pid_path) as f:
            assert f.read().strip() == winners[0]

    def test_claim_removes_leftover_socket(self, server):
        with open(server.socket_path, "w") as f:
            f.write("")
        server._claim_pid()
        assert not os.path.exists(server.socket_path)

    def test_cleanup_only_removes_own_pid(self, server):
        # pid file belongs to another (stale) daemon; cleanup must keep it.
        with open(server.pid_path, "w") as f:
            f.write("999999999")
        server._cleanup_files()
        assert os.path.exists(server.pid_path)

    def test_cleanup_keeps_unbound_socket(self, server):
        # A daemon that never bound must not delete the session socket.
        with open(server.socket_path, "w") as f:
            f.write("")
        server._cleanup_files()
        assert os.path.exists(server.socket_path)


class TestConnectionTimeout:
    def test_idle_client_does_not_block_other_commands(self, server, monkeypatch):
        """A client that connects but never sends must not block the daemon."""
        monkeypatch.setattr(server_module, "CONNECTION_TIMEOUT", 0.5)

        def run():
            with patch.object(signal, "signal"):  # main-thread only
                server.start()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        deadline = time.time() + 5
        while not os.path.exists(server.socket_path) and time.time() < deadline:
            time.sleep(0.05)

        def send(command: dict) -> dict:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect(server.socket_path)
                s.sendall(json.dumps(command).encode() + b"\n")
                return json.loads(s.makefile().readline())

        idle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        idle.connect(server.socket_path)
        try:
            # No browser is launched, so "title" answers with an error at once
            # (once the daemon drops the idle connection).
            resp = send({"id": "r1", "action": "title", "params": {}})
            assert resp["id"] == "r1"
        finally:
            idle.close()
            send({"id": "r2", "action": "close", "params": {}})
            thread.join(timeout=5)
