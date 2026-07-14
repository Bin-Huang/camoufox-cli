"""Tests for daemon pid-file claiming (startup race hardening)."""

import os
import subprocess
import sys
import time

import pytest

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
