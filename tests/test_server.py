"""Tests for daemon pid-file claiming (startup race hardening)."""

import os
import time

import pytest

from camoufox_cli.server import DaemonServer


@pytest.fixture
def server():
    session = f"claim-test-{os.getpid()}-{time.monotonic_ns()}"
    srv = DaemonServer(session=session)
    yield srv
    for path in (srv.pid_path, srv.socket_path):
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
