"""CLI client: parses args, starts daemon if needed, sends command via Unix socket."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time


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


def spawn_daemon(session: str, headed: bool, timeout: int, persistent: str | None) -> None:
    cmd = [sys.executable, "-m", "camoufox_cli", "--session", session, "--timeout", str(timeout)]
    if headed:
        cmd.append("--headed")
    if persistent:
        cmd.extend(["--persistent", persistent])

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


def ensure_daemon(session: str, headed: bool, timeout: int, persistent: str | None) -> None:
    sock_path = get_socket_path(session)
    if os.path.exists(sock_path):
        # Verify daemon is actually alive by trying to connect
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(sock_path)
            s.close()
            return
        except (ConnectionRefusedError, OSError):
            # Stale socket from a dead daemon — clean up
            try:
                os.unlink(sock_path)
            except FileNotFoundError:
                pass
    spawn_daemon(session, headed, timeout, persistent)


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
    """Parse CLI args into (flags, command). Returns (flags_dict, command_json)."""
    flags = {"session": "default", "headed": False, "timeout": 1800, "json": False, "persistent": None}
    rest = []

    i = 0
    while i < len(args):
        if args[i] == "--session":
            i += 1
            if i >= len(args):
                print("Error: --session requires a value", file=sys.stderr)
                sys.exit(1)
            flags["session"] = args[i]
        elif args[i] == "--headed":
            flags["headed"] = True
        elif args[i] == "--timeout":
            i += 1
            if i >= len(args):
                print("Error: --timeout requires a value", file=sys.stderr)
                sys.exit(1)
            flags["timeout"] = int(args[i])
        elif args[i] == "--json":
            flags["json"] = True
        elif args[i] == "--persistent":
            i += 1
            if i >= len(args):
                print("Error: --persistent requires a value", file=sys.stderr)
                sys.exit(1)
            flags["persistent"] = args[i]
        else:
            rest.append(args[i])
        i += 1

    if not rest:
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    action = rest[0]
    cmd = build_command(action, rest)
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
        case "close-tab":
            return {"id": "r1", "action": "close-tab", "params": {}}

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


def main():
    args = sys.argv[1:]
    flags, command = parse_args(args)

    action = command.get("action", "")

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
        close_cmd = {"id": "r1", "action": "close", "params": {}}
        for session in sessions:
            sock_path = get_socket_path(session)
            try:
                send_command(sock_path, close_cmd)
            except Exception as e:
                print(f"Failed to close session {session}: {e}", file=sys.stderr)
        return

    # Ensure daemon is running
    ensure_daemon(flags["session"], flags["headed"], flags["timeout"], flags["persistent"])

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
            if attempt < 4:
                time.sleep(0.2 * (attempt + 1))

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
  close [--all]           Close browser and daemon (--all: all sessions)

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
  close-tab               Close current tab

Session:
  sessions                List active sessions
  cookies [import|export] Manage cookies

Flags:
  --session <name>     Session name (default: "default")
  --headed             Show browser window
  --timeout <secs>     Daemon idle timeout (default: 1800)
  --json               Output as JSON
  --persistent <path>  Use persistent browser profile"""
