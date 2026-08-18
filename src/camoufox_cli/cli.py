"""CLI client: parses args, starts daemon if needed, sends command via Unix socket."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

from .config import load_defaults


SOCKET_PREFIX = "/tmp/camoufox-cli-"


def get_socket_path(session: str) -> str:
    return f"{SOCKET_PREFIX}{session}.sock"


def send_command(sock_path: str, command: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    s.sendall(json.dumps(command).encode() + b"\n")
    s.shutdown(socket.SHUT_WR)
    data = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
    s.close()
    return json.loads(data.decode())


def spawn_daemon(session: str, headed: bool, timeout: int, persistent: str | None, proxy: str | None = None, geoip: bool = True, locale: str | None = None) -> None:
    cmd = [sys.executable, "-m", "camoufox_cli", "--session", session, "--timeout", str(timeout)]
    if headed:
        cmd.append("--headed")
    if persistent:
        cmd.extend(["--persistent", persistent])
    if proxy:
        cmd.extend(["--proxy", proxy])
    if not geoip:
        cmd.append("--no-geoip")
    if locale:
        cmd.extend(["--locale", locale])

    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    sock_path = get_socket_path(session)
    for _ in range(50):
        if os.path.exists(sock_path):
            return
        time.sleep(0.1)

    print("Error: Daemon did not start within 5 seconds", file=sys.stderr)
    sys.exit(1)


def ensure_daemon(session: str, headed: bool, timeout: int, persistent: str | None, proxy: str | None = None, geoip: bool = True, locale: str | None = None) -> None:
    sock_path = get_socket_path(session)
    if os.path.exists(sock_path):
        # Verify the daemon is actually alive. Retry a few times before giving
        # up: a momentarily busy daemon (accept backlog full while it handles a
        # slow command) can transiently refuse a connect, and we must not delete
        # a live daemon's socket and respawn — the respawn would lose the pid
        # claim and exit, leaving the session unreachable.
        for attempt in range(3):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect(sock_path)
                s.close()
                return
            except (ConnectionRefusedError, OSError):
                if attempt < 2:
                    time.sleep(0.2 * (attempt + 1))
        # Consistently unreachable — treat as a stale socket from a dead daemon.
        try:
            os.unlink(sock_path)
        except FileNotFoundError:
            pass
    spawn_daemon(session, headed, timeout, persistent, proxy, geoip, locale)


def get_version() -> str:
    """Version from installed package metadata; pyproject isn't shipped in the wheel."""
    from importlib.metadata import version, PackageNotFoundError

    try:
        return version("camoufox-cli")
    except PackageNotFoundError:
        return "unknown"


def list_sessions() -> list[str]:
    sessions = []
    try:
        for name in os.listdir("/tmp"):
            if name.startswith("camoufox-cli-") and name.endswith(".sock"):
                sessions.append(name[len("camoufox-cli-"):-len(".sock")])
    except OSError:
        pass
    sessions.sort()
    return sessions


def parse_args(args: list[str]) -> tuple[dict, dict]:
    """Parse CLI args into (flags, command). Returns (flags_dict, command_json).

    Flag precedence: command line > config file (per-session block, then the
    ``default`` block) > built-in defaults. Only flags explicitly passed on the
    command line are collected here, so they always win over config; see
    ``config.load_defaults``.
    """
    builtin = {"session": "default", "tab": "default", "headed": False, "timeout": 1800, "json": False, "persistent": None, "proxy": None, "geoip": True, "locale": None}
    cli: dict = {}
    rest = []

    i = 0
    while i < len(args):
        if args[i] == "--session":
            i += 1
            if i >= len(args):
                print("Error: --session requires a value", file=sys.stderr)
                sys.exit(1)
            cli["session"] = args[i]
        elif args[i] == "--tab":
            i += 1
            if i >= len(args):
                print("Error: --tab requires a value", file=sys.stderr)
                sys.exit(1)
            cli["tab"] = args[i]
        elif args[i] == "--headed":
            cli["headed"] = True
        elif args[i] == "--timeout":
            i += 1
            if i >= len(args):
                print("Error: --timeout requires a value", file=sys.stderr)
                sys.exit(1)
            cli["timeout"] = int(args[i])
        elif args[i] == "--json":
            cli["json"] = True
        elif args[i] == "--persistent":
            # Optional value: if next arg looks like a path, use it; otherwise use default
            if i + 1 < len(args) and ("/" in args[i + 1] or args[i + 1].startswith((".", "~"))):
                i += 1
                cli["persistent"] = args[i]
            else:
                cli["persistent"] = ""
        elif args[i] == "--proxy":
            i += 1
            if i >= len(args):
                print("Error: --proxy requires a value", file=sys.stderr)
                sys.exit(1)
            cli["proxy"] = args[i]
        elif args[i] == "--no-geoip":
            cli["geoip"] = False
        elif args[i] == "--locale":
            i += 1
            if i >= len(args):
                print("Error: --locale requires a value", file=sys.stderr)
                sys.exit(1)
            cli["locale"] = args[i]
        else:
            rest.append(args[i])
        i += 1

    if not rest:
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    # session selects which config block applies, so it comes only from the CLI.
    session = cli.get("session", builtin["session"])
    flags = {**builtin, **load_defaults(session), **cli}

    action = rest[0]
    cmd = build_command(action, rest)
    # Route the command to a named tab within the session's shared browser.
    cmd["tab"] = flags["tab"]
    return flags, cmd


def build_command(action: str, rest: list[str]) -> dict:
    """Build JSON command from action and remaining args."""
    match action:
        # Navigation
        case "open":
            url = _require(rest, 1, "Usage: camoufox-cli open <url>")
            return {"id": "r1", "action": "open", "params": {"url": url}}
        case "back":
            return {"id": "r1", "action": "back", "params": {}}
        case "forward":
            return {"id": "r1", "action": "forward", "params": {}}
        case "reload":
            return {"id": "r1", "action": "reload", "params": {}}
        case "url":
            return {"id": "r1", "action": "url", "params": {}}
        case "title":
            return {"id": "r1", "action": "title", "params": {}}
        case "close":
            all_flag = "--all" in rest
            return {"id": "r1", "action": "close", "params": {"all": all_flag}}

        # Snapshot
        case "snapshot":
            interactive = "-i" in rest
            selector = None
            if "-s" in rest:
                idx = rest.index("-s")
                selector = _require(rest, idx + 1, "Usage: camoufox-cli snapshot -s <selector>")
            params = {"interactive": interactive}
            if selector:
                params["selector"] = selector
            return {"id": "r1", "action": "snapshot", "params": params}

        # Interaction
        case "click":
            ref = _require(rest, 1, "Usage: camoufox-cli click @e1")
            return {"id": "r1", "action": "click", "params": {"ref": ref}}
        case "fill":
            ref = _require(rest, 1, "Usage: camoufox-cli fill @e1 \"text\"")
            text = _require(rest, 2, "Usage: camoufox-cli fill @e1 \"text\"")
            return {"id": "r1", "action": "fill", "params": {"ref": ref, "text": text}}
        case "type":
            ref = _require(rest, 1, "Usage: camoufox-cli type @e1 \"text\"")
            text = _require(rest, 2, "Usage: camoufox-cli type @e1 \"text\"")
            return {"id": "r1", "action": "type", "params": {"ref": ref, "text": text}}
        case "select":
            ref = _require(rest, 1, "Usage: camoufox-cli select @e1 \"option\"")
            value = _require(rest, 2, "Usage: camoufox-cli select @e1 \"option\"")
            return {"id": "r1", "action": "select", "params": {"ref": ref, "value": value}}
        case "check":
            ref = _require(rest, 1, "Usage: camoufox-cli check @e1")
            return {"id": "r1", "action": "check", "params": {"ref": ref}}
        case "hover":
            ref = _require(rest, 1, "Usage: camoufox-cli hover @e1")
            return {"id": "r1", "action": "hover", "params": {"ref": ref}}
        case "press":
            key = _require(rest, 1, "Usage: camoufox-cli press Enter")
            return {"id": "r1", "action": "press", "params": {"key": key}}

        # Data extraction
        case "text":
            target = _require(rest, 1, "Usage: camoufox-cli text @e1 | camoufox-cli text body")
            return {"id": "r1", "action": "text", "params": {"target": target}}
        case "eval":
            expr = _require(rest, 1, "Usage: camoufox-cli eval \"document.title\"")
            return {"id": "r1", "action": "eval", "params": {"expression": expr}}
        case "screenshot":
            params = {}
            for arg in rest[1:]:
                if arg == "--full":
                    params["full_page"] = True
                else:
                    params["path"] = arg
            return {"id": "r1", "action": "screenshot", "params": params}
        case "pdf":
            path = _require(rest, 1, "Usage: camoufox-cli pdf output.pdf")
            return {"id": "r1", "action": "pdf", "params": {"path": path}}

        # Scroll & Wait
        case "scroll":
            direction = _require(rest, 1, "Usage: camoufox-cli scroll down [px]")
            amount = int(rest[2]) if len(rest) > 2 else 500
            return {"id": "r1", "action": "scroll", "params": {"direction": direction, "amount": amount}}
        case "wait":
            target = _require(rest, 1, "Usage: camoufox-cli wait @e1 | camoufox-cli wait 2000 | camoufox-cli wait --url \"pattern\"")
            if target == "--url":
                pattern = _require(rest, 2, "Usage: camoufox-cli wait --url \"*/dashboard\"")
                return {"id": "r1", "action": "wait", "params": {"url": pattern}}
            elif target.startswith("@"):
                return {"id": "r1", "action": "wait", "params": {"ref": target}}
            elif target[0].isdigit():
                return {"id": "r1", "action": "wait", "params": {"ms": int(target)}}
            else:
                return {"id": "r1", "action": "wait", "params": {"selector": target}}

        # Tab management
        case "tabs":
            return {"id": "r1", "action": "tabs", "params": {}}
        case "switch":
            index = _require(rest, 1, "Usage: camoufox-cli switch <tab-index>")
            return {"id": "r1", "action": "switch", "params": {"index": int(index)}}
        # Install
        case "install":
            return {"id": "r1", "action": "install", "params": {"with_deps": "--with-deps" in rest}}

        # Session & Cookies
        case "sessions":
            return {"id": "r1", "action": "sessions", "params": {}}
        case "cookies":
            if len(rest) > 1 and rest[1] == "import":
                path = _require(rest, 2, "Usage: camoufox-cli cookies import file.json")
                return {"id": "r1", "action": "cookies", "params": {"op": "import", "path": path}}
            elif len(rest) > 1 and rest[1] == "export":
                path = _require(rest, 2, "Usage: camoufox-cli cookies export file.json")
                return {"id": "r1", "action": "cookies", "params": {"op": "export", "path": path}}
            else:
                return {"id": "r1", "action": "cookies", "params": {"op": "list"}}

        case _:
            print(f"Unknown command: {action}\n{USAGE}", file=sys.stderr)
            sys.exit(1)


def _require(args: list[str], idx: int, usage: str) -> str:
    if idx >= len(args):
        print(usage, file=sys.stderr)
        sys.exit(1)
    return args[idx]


def print_response(response: dict, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return

    if not response.get("success"):
        print(f"Error: {response.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)

    data = response.get("data")
    if not data:
        return

    if "snapshot" in data:
        print(data["snapshot"])
    elif "text" in data:
        print(data["text"])
    elif "result" in data:
        v = data["result"]
        print("null" if v is None else json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
    elif data.get("closed"):
        pass  # silent
    elif "url" in data:
        if "title" in data:
            print(data["title"])
        print(data["url"])
    elif "title" in data:
        print(data["title"])
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


_APT_DEPS = [
    "libxcb-shm0", "libx11-xcb1", "libx11-6", "libxcb1", "libxext6",
    "libxrandr2", "libxcomposite1", "libxcursor1", "libxdamage1", "libxfixes3",
    "libxi6", "libgtk-3-0", "libpangocairo-1.0-0", "libpango-1.0-0",
    "libatk1.0-0", "libcairo-gobject2", "libcairo2", "libgdk-pixbuf-2.0-0",
    "libxrender1", "libfreetype6", "libfontconfig1", "libdbus-1-3",
    "libnss3", "libnspr4", "libatk-bridge2.0-0", "libdrm2", "libxkbcommon0",
    "libatspi2.0-0", "libcups2", "libxshmfence1", "libgbm1", "libasound2",
]

_DNF_DEPS = [
    "nss", "nspr", "atk", "at-spi2-atk", "cups-libs", "libdrm",
    "libXcomposite", "libXdamage", "libXrandr", "mesa-libgbm", "pango",
    "alsa-lib", "libxkbcommon", "libxcb", "libX11-xcb", "libX11",
    "libXext", "libXcursor", "libXfixes", "libXi", "gtk3", "cairo-gobject",
]

_YUM_DEPS = [
    "nss", "nspr", "atk", "at-spi2-atk", "cups-libs", "libdrm",
    "libXcomposite", "libXdamage", "libXrandr", "mesa-libgbm", "pango",
    "alsa-lib", "libxkbcommon",
]


def _apt_installable(pkg: str) -> bool:
    """True when a dry-run install of the package resolves."""
    result = subprocess.run(
        ["apt-get", "install", "-s", "-y", pkg],
        capture_output=True,
    )
    return result.returncode == 0


def _resolve_apt_deps(deps: list[str]) -> list[str]:
    """Map package names to what this system's apt actually knows.

    Ubuntu 24.04's 64-bit time_t transition renamed many runtime libs with a
    t64 suffix (libasound2 -> libasound2t64, libgtk-3-0 -> libgtk-3-0t64, ...)
    WITHOUT a Provides for the old name, so installing the old names fails.
    Fast path: if the plain list resolves as a whole (Debian, older Ubuntu),
    use it. Otherwise resolve per package, preferring the plain name and
    falling back to <name>t64. Unknown-either-way names are kept so apt
    reports the real error instead of this helper guessing silently.
    """
    result = subprocess.run(
        ["apt-get", "install", "-s", "-y", *deps],
        capture_output=True,
    )
    if result.returncode == 0:
        return deps
    return [
        dep if _apt_installable(dep)
        else (f"{dep}t64" if _apt_installable(f"{dep}t64") else dep)
        for dep in deps
    ]


def _run_as_root(argv: list[str]) -> None:
    """Run a privileged package-manager command.

    Prefer bare invocation when already root (Docker/CI images rarely ship
    sudo). Fall back to sudo for unprivileged interactive installs.
    """
    if os.geteuid() == 0:
        subprocess.run(argv, check=True)
    else:
        subprocess.run(["sudo", *argv], check=True)


def _install_system_deps() -> None:
    import platform
    import shutil

    if platform.system() != "Linux":
        print("[camoufox-cli] System dependencies are only needed on Linux, skipping.", file=sys.stderr)
        return

    print("[camoufox-cli] Installing system dependencies...", file=sys.stderr)

    if shutil.which("apt-get"):
        _run_as_root(["apt-get", "update", "-y"])
        # Resolve AFTER update: dry-run resolution needs a populated apt cache.
        deps = _resolve_apt_deps(_APT_DEPS)
        _run_as_root(["apt-get", "install", "-y", *deps])
    elif shutil.which("dnf"):
        _run_as_root(["dnf", "install", "-y", *_DNF_DEPS])
    elif shutil.which("yum"):
        _run_as_root(["yum", "install", "-y", *_YUM_DEPS])
    else:
        print("[camoufox-cli] Could not detect a supported package manager (apt-get, dnf, yum).", file=sys.stderr)
        sys.exit(1)

    print("[camoufox-cli] System dependencies installed.", file=sys.stderr)


def main():
    args = sys.argv[1:]

    # Short-circuit before parse_args: --version has no command and needs no daemon.
    if "--version" in args:
        print(get_version())
        return

    flags, command = parse_args(args)

    # Resolve default persistent path
    if flags["persistent"] == "":
        flags["persistent"] = os.path.expanduser(f"~/.camoufox-cli/profiles/{flags['session']}")

    action = command.get("action", "")

    # Client-side: install
    if action == "install":
        print("[camoufox-cli] Downloading browser...", file=sys.stderr)
        from .install import install_browser
        install_browser()
        print("[camoufox-cli] Browser installed.", file=sys.stderr)
        if command.get("params", {}).get("with_deps"):
            _install_system_deps()
        return

    # Client-side: sessions
    if action == "sessions":
        sessions = list_sessions()
        if flags["json"]:
            print(json.dumps(sessions, indent=2))
        elif not sessions:
            print("No active sessions.")
        else:
            for s in sessions:
                print(s)
        return

    # Client-side: close --all
    if action == "close" and command.get("params", {}).get("all"):
        sessions = list_sessions()
        if not sessions:
            print("No active sessions.")
            return
        # Force: tear each session's browser down regardless of open tabs.
        close_cmd = {"id": "r1", "action": "close", "params": {"force": True}}
        for session in sessions:
            sock_path = get_socket_path(session)
            try:
                send_command(sock_path, close_cmd)
            except Exception as e:
                print(f"Failed to close session {session}: {e}", file=sys.stderr)
        return

    # Ensure daemon is running
    ensure_daemon(flags["session"], flags["headed"], flags["timeout"], flags["persistent"], flags["proxy"], flags["geoip"], flags["locale"])

    sock_path = get_socket_path(flags["session"])

    # Send command with retry
    last_err = ""
    for attempt in range(5):
        try:
            response = send_command(sock_path, command)
            print_response(response, flags["json"])
            return
        except Exception as e:
            last_err = str(e)
            # close is idempotent: if the daemon is gone (socket removed),
            # there is nothing left to close — that IS success. This is the
            # receipt for a close that raced the last-tab shutdown: the daemon
            # may exit after releasing our tab but before responding.
            if action == "close" and not os.path.exists(sock_path):
                if flags["json"]:
                    print(json.dumps({"id": "r1", "success": True, "data": {"closed": True}}))
                return
            if attempt < 4:
                time.sleep(0.2 * (attempt + 1))

    # Same idempotent-close check once more: the daemon may have finished
    # unlinking its socket only while we were burning the retry budget.
    if action == "close" and not os.path.exists(sock_path):
        if flags["json"]:
            print(json.dumps({"id": "r1", "success": True, "data": {"closed": True}}))
        return

    print(f"Error: Failed to connect to daemon after 5 attempts: {last_err}", file=sys.stderr)
    sys.exit(1)


USAGE = """\
Usage: camoufox-cli [flags] <command> [args]

Navigation:
  open <url>              Navigate to URL
  back                    Go back
  forward                 Go forward
  reload                  Reload page
  url                     Print current URL
  title                   Print page title
  close [--all]           Close your tab; browser and daemon exit when the
                          last tab closes (--all: force-close all sessions)

Snapshot:
  snapshot [-i] [-s sel]  Aria tree (-i interactive, -s scoped)

Interaction:
  click @ref              Click element
  fill @ref "text"        Clear + type into input
  type @ref "text"        Type without clearing
  select @ref "option"    Select dropdown option
  check @ref              Toggle checkbox
  hover @ref              Hover over element
  press <key>             Press key (e.g. Enter, Control+a)

Data:
  text @ref|selector      Get text content
  eval "js expression"    Execute JavaScript
  screenshot [--full] [f] Screenshot to file or stdout
  pdf <file>              Save page as PDF

Scroll & Wait:
  scroll <dir> [px]       Scroll up/down (default 500px)
  wait <ms|@ref|--url p>  Wait for time/element/URL

Tabs:
  tabs                    List open tabs
  switch <index>          Switch to tab

Session:
  sessions                List active sessions
  cookies [import|export] Manage cookies

Setup:
  install [--with-deps]   Download browser (--with-deps: system libs)

Flags:
  --session <name>     Session name (default: "default")
  --tab <name>         Named tab within the session's shared browser: same
                       fingerprint and cookies/login, independent page/refs/
                       history. Give each concurrent agent its own tab name.
  --headed             Show browser window
  --timeout <secs>     Daemon idle timeout (default: 1800)
  --json               Output as JSON
  --persistent [path]  Use persistent browser profile (default: ~/.camoufox-cli/profiles/<session>)
  --proxy <url>        Proxy server (e.g. http://host:port or https://host:443)
  --no-geoip           Disable automatic GeoIP spoofing (auto-enabled with --proxy)
  --locale <tag>       Force browser locale (e.g. "en-US" or "en-US,zh-CN")
  --version            Print version and exit

Config file:
  ~/.camoufox-cli/config.json sets defaults for the flags above (override the
  path with $CAMOUFOX_CLI_CONFIG). Command-line flags always take precedence.
  Use a "default" block plus optional per-session blocks under "sessions"."""
