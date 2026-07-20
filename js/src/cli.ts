#!/usr/bin/env node
/** CLI client: parses args, starts daemon if needed, sends command via Unix socket. */

import * as net from "node:net";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { execFileSync, spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { loadDefaults } from "./config.js";

const SOCKET_PREFIX = "/tmp/camoufox-cli-";

export function getSocketPath(session: string): string {
  return `${SOCKET_PREFIX}${session}.sock`;
}

function sendCommand(sockPath: string, command: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const client = net.createConnection(sockPath, () => {
      client.end(JSON.stringify(command) + "\n");
    });

    let data = "";
    client.on("data", (chunk) => { data += chunk.toString(); });
    client.on("end", () => {
      try { resolve(JSON.parse(data)); }
      catch (e) { reject(new Error(`Invalid response: ${data}`)); }
    });
    client.on("error", reject);
  });
}

function spawnDaemon(session: string, headed: boolean, timeout: number, persistent: string | null, proxy: string | null = null, geoip: boolean = true, locale: string | null = null): Promise<void> {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const daemonPath = path.join(__dirname, "daemon.js");

  const args = ["--session", session, "--timeout", String(timeout)];
  if (headed) args.push("--headed");
  if (persistent) args.push("--persistent", persistent);
  if (proxy) args.push("--proxy", proxy);
  if (!geoip) args.push("--no-geoip");
  if (locale) args.push("--locale", locale);

  spawn("node", [daemonPath, ...args], {
    detached: true,
    stdio: "ignore",
  }).unref();

  const sockPath = getSocketPath(session);
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      if (fs.existsSync(sockPath)) return resolve();
      attempts++;
      if (attempts >= 50) return reject(new Error("Daemon did not start within 5 seconds"));
      setTimeout(check, 100);
    };
    check();
  });
}

async function ensureDaemon(session: string, headed: boolean, timeout: number, persistent: string | null, proxy: string | null = null, geoip: boolean = true, locale: string | null = null): Promise<void> {
  const sockPath = getSocketPath(session);
  if (fs.existsSync(sockPath)) {
    // Verify the daemon is alive. Retry a few times before giving up: a
    // momentarily busy daemon can transiently refuse a connect, and deleting a
    // live daemon's socket would make the respawn lose the pid claim and exit,
    // leaving the session unreachable.
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await new Promise<void>((resolve, reject) => {
          const s = net.createConnection(sockPath, () => { s.destroy(); resolve(); });
          s.on("error", reject);
          s.setTimeout(2000, () => { s.destroy(); reject(new Error("timeout")); });
        });
        return;
      } catch {
        if (attempt < 2) await new Promise((r) => setTimeout(r, 200 * (attempt + 1)));
      }
    }
    // Consistently unreachable — treat as a stale socket from a dead daemon.
    try { fs.unlinkSync(sockPath); } catch {}
  }
  await spawnDaemon(session, headed, timeout, persistent, proxy, geoip, locale);
}

export function listSessions(): string[] {
  const sessions: string[] = [];
  try {
    for (const name of fs.readdirSync("/tmp")) {
      if (name.startsWith("camoufox-cli-") && name.endsWith(".sock")) {
        sessions.push(name.slice("camoufox-cli-".length, -".sock".length));
      }
    }
  } catch {}
  return sessions.sort();
}

export function getVersion(): string {
  // package.json ships in the npm package and sits one level above both src/ and dist/.
  try {
    const pkgPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "package.json");
    return JSON.parse(fs.readFileSync(pkgPath, "utf8")).version ?? "unknown";
  } catch {
    return "unknown";
  }
}

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------

export interface Flags {
  session: string;
  tab: string;
  headed: boolean;
  timeout: number;
  json: boolean;
  persistent: string | null;
  proxy: string | null;
  geoip: boolean;
  locale: string | null;
}

export function parseArgs(argv: string[]): { flags: Flags; command: Record<string, unknown> } {
  // Flag precedence: command line > config file (per-session block, then the
  // `default` block) > built-in defaults. Only flags explicitly passed on the
  // command line are collected here, so they always win over config.
  const builtin: Flags = { session: "default", tab: "default", headed: false, timeout: 1800, json: false, persistent: null, proxy: null, geoip: true, locale: null };
  const cli: Partial<Flags> = {};
  const rest: string[] = [];

  let i = 0;
  while (i < argv.length) {
    switch (argv[i]) {
      case "--session":
        cli.session = argv[++i] ?? (process.stderr.write("Error: --session requires a value\n"), process.exit(1), "");
        break;
      case "--tab":
        cli.tab = argv[++i] ?? (process.stderr.write("Error: --tab requires a value\n"), process.exit(1), "");
        break;
      case "--headed":
        cli.headed = true;
        break;
      case "--timeout":
        cli.timeout = parseInt(argv[++i] ?? "1800", 10);
        break;
      case "--json":
        cli.json = true;
        break;
      case "--persistent": {
        // Optional value: if next arg looks like a path, use it; otherwise use default
        const next = argv[i + 1];
        if (next && (next.includes("/") || next.startsWith(".") || next.startsWith("~"))) {
          cli.persistent = argv[++i];
        } else {
          cli.persistent = "";
        }
        break;
      }
      case "--proxy":
        cli.proxy = argv[++i] ?? null;
        break;
      case "--no-geoip":
        cli.geoip = false;
        break;
      case "--locale":
        cli.locale = argv[++i] ?? (process.stderr.write("Error: --locale requires a value\n"), process.exit(1), "");
        break;
      default:
        rest.push(argv[i]);
    }
    i++;
  }

  if (rest.length === 0) {
    process.stderr.write(USAGE + "\n");
    process.exit(1);
  }

  // session selects which config block applies, so it comes only from the CLI.
  const session = cli.session ?? builtin.session;
  const flags: Flags = { ...builtin, ...loadDefaults(session), ...cli };

  const command = buildCommand(rest[0], rest);
  // Route the command to a named tab within the session's shared browser.
  command.tab = flags.tab;
  return { flags, command };
}

function require_(args: string[], idx: number, usage: string): string {
  if (idx >= args.length) {
    process.stderr.write(usage + "\n");
    process.exit(1);
  }
  return args[idx];
}

export function buildCommand(action: string, rest: string[]): Record<string, unknown> {
  switch (action) {
    case "open":
      return { id: "r1", action: "open", params: { url: require_(rest, 1, "Usage: camoufox-cli open <url>") } };
    case "back":
      return { id: "r1", action: "back", params: {} };
    case "forward":
      return { id: "r1", action: "forward", params: {} };
    case "reload":
      return { id: "r1", action: "reload", params: {} };
    case "url":
      return { id: "r1", action: "url", params: {} };
    case "title":
      return { id: "r1", action: "title", params: {} };
    case "close":
      return { id: "r1", action: "close", params: { all: rest.includes("--all") } };

    case "snapshot": {
      const interactive = rest.includes("-i");
      let selector: string | undefined;
      const sIdx = rest.indexOf("-s");
      if (sIdx >= 0) selector = require_(rest, sIdx + 1, "Usage: camoufox-cli snapshot -s <selector>");
      const params: Record<string, unknown> = { interactive };
      if (selector) params.selector = selector;
      return { id: "r1", action: "snapshot", params };
    }

    case "click":
      return { id: "r1", action: "click", params: { ref: require_(rest, 1, "Usage: camoufox-cli click @e1") } };
    case "fill":
      return { id: "r1", action: "fill", params: { ref: require_(rest, 1, 'Usage: camoufox-cli fill @e1 "text"'), text: require_(rest, 2, 'Usage: camoufox-cli fill @e1 "text"') } };
    case "type":
      return { id: "r1", action: "type", params: { ref: require_(rest, 1, 'Usage: camoufox-cli type @e1 "text"'), text: require_(rest, 2, 'Usage: camoufox-cli type @e1 "text"') } };
    case "select":
      return { id: "r1", action: "select", params: { ref: require_(rest, 1, 'Usage: camoufox-cli select @e1 "option"'), value: require_(rest, 2, 'Usage: camoufox-cli select @e1 "option"') } };
    case "check":
      return { id: "r1", action: "check", params: { ref: require_(rest, 1, "Usage: camoufox-cli check @e1") } };
    case "hover":
      return { id: "r1", action: "hover", params: { ref: require_(rest, 1, "Usage: camoufox-cli hover @e1") } };
    case "press":
      return { id: "r1", action: "press", params: { key: require_(rest, 1, "Usage: camoufox-cli press Enter") } };

    case "text":
      return { id: "r1", action: "text", params: { target: require_(rest, 1, "Usage: camoufox-cli text @e1") } };
    case "eval":
      return { id: "r1", action: "eval", params: { expression: require_(rest, 1, 'Usage: camoufox-cli eval "document.title"') } };
    case "screenshot": {
      const params: Record<string, unknown> = {};
      for (const arg of rest.slice(1)) {
        if (arg === "--full") params.full_page = true;
        else params.path = arg;
      }
      return { id: "r1", action: "screenshot", params };
    }
    case "pdf":
      return { id: "r1", action: "pdf", params: { path: require_(rest, 1, "Usage: camoufox-cli pdf output.pdf") } };

    case "scroll":
      return { id: "r1", action: "scroll", params: { direction: require_(rest, 1, "Usage: camoufox-cli scroll down [px]"), amount: rest.length > 2 ? parseInt(rest[2], 10) : 500 } };
    case "wait": {
      const target = require_(rest, 1, 'Usage: camoufox-cli wait @e1 | camoufox-cli wait 2000 | camoufox-cli wait --url "pattern"');
      if (target === "--url") return { id: "r1", action: "wait", params: { url: require_(rest, 2, 'Usage: camoufox-cli wait --url "*/dashboard"') } };
      if (target.startsWith("@")) return { id: "r1", action: "wait", params: { ref: target } };
      if (/^\d/.test(target)) return { id: "r1", action: "wait", params: { ms: parseInt(target, 10) } };
      return { id: "r1", action: "wait", params: { selector: target } };
    }

    case "tabs":
      return { id: "r1", action: "tabs", params: {} };
    case "switch":
      return { id: "r1", action: "switch", params: { index: parseInt(require_(rest, 1, "Usage: camoufox-cli switch <tab-index>"), 10) } };
    case "sessions":
      return { id: "r1", action: "sessions", params: {} };
    case "install":
      return { id: "r1", action: "install", params: { with_deps: rest.includes("--with-deps") } };
    case "cookies": {
      if (rest.length > 1 && rest[1] === "import")
        return { id: "r1", action: "cookies", params: { op: "import", path: require_(rest, 2, "Usage: camoufox-cli cookies import file.json") } };
      if (rest.length > 1 && rest[1] === "export")
        return { id: "r1", action: "cookies", params: { op: "export", path: require_(rest, 2, "Usage: camoufox-cli cookies export file.json") } };
      return { id: "r1", action: "cookies", params: { op: "list" } };
    }

    default:
      process.stderr.write(`Unknown command: ${action}\n${USAGE}\n`);
      process.exit(1);
  }
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

export function printResponse(response: Record<string, unknown>, jsonMode: boolean): void {
  if (jsonMode) {
    console.log(JSON.stringify(response, null, 2));
    return;
  }

  if (!response.success) {
    process.stderr.write(`Error: ${response.error || "Unknown error"}\n`);
    process.exit(1);
  }

  const data = response.data as Record<string, unknown> | undefined;
  if (!data) return;

  if ("snapshot" in data) {
    console.log(data.snapshot);
  } else if ("text" in data) {
    console.log(data.text);
  } else if ("result" in data) {
    const v = data.result;
    console.log(v === null ? "null" : typeof v === "string" ? v : JSON.stringify(v));
  } else if (data.closed) {
    // silent
  } else if ("url" in data) {
    if ("title" in data) console.log(data.title);
    console.log(data.url);
  } else if ("title" in data) {
    console.log(data.title);
  } else {
    console.log(JSON.stringify(data, null, 2));
  }
}

// ---------------------------------------------------------------------------
// System dependencies
// ---------------------------------------------------------------------------

const APT_DEPS = [
  "libxcb-shm0", "libx11-xcb1", "libx11-6", "libxcb1", "libxext6",
  "libxrandr2", "libxcomposite1", "libxcursor1", "libxdamage1", "libxfixes3",
  "libxi6", "libgtk-3-0", "libpangocairo-1.0-0", "libpango-1.0-0",
  "libatk1.0-0", "libcairo-gobject2", "libcairo2", "libgdk-pixbuf-2.0-0",
  "libxrender1", "libfreetype6", "libfontconfig1", "libdbus-1-3",
  "libnss3", "libnspr4", "libatk-bridge2.0-0", "libdrm2", "libxkbcommon0",
  "libatspi2.0-0", "libcups2", "libxshmfence1", "libgbm1", "libasound2",
];

const DNF_DEPS = [
  "nss", "nspr", "atk", "at-spi2-atk", "cups-libs", "libdrm",
  "libXcomposite", "libXdamage", "libXrandr", "mesa-libgbm", "pango",
  "alsa-lib", "libxkbcommon", "libxcb", "libX11-xcb", "libX11",
  "libXext", "libXcursor", "libXfixes", "libXi", "gtk3", "cairo-gobject",
];

const YUM_DEPS = [
  "nss", "nspr", "atk", "at-spi2-atk", "cups-libs", "libdrm",
  "libXcomposite", "libXdamage", "libXrandr", "mesa-libgbm", "pango",
  "alsa-lib", "libxkbcommon",
];

/** True when a dry-run install of the package resolves. */
function aptInstallable(pkg: string): boolean {
  try {
    execFileSync("apt-get", ["install", "-s", "-y", pkg], { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

/**
 * Map package names to what this system's apt actually knows.
 *
 * Ubuntu 24.04's 64-bit time_t transition renamed many runtime libs with a
 * t64 suffix (libasound2 -> libasound2t64, libgtk-3-0 -> libgtk-3-0t64, ...)
 * WITHOUT a Provides for the old name, so installing the old names fails.
 * Fast path: if the plain list resolves as a whole (Debian, older Ubuntu),
 * use it. Otherwise resolve per package, preferring the plain name and
 * falling back to <name>t64. Unknown-either-way names are kept so apt
 * reports the real error instead of this helper guessing silently.
 */
function resolveAptDeps(deps: string[]): string[] {
  try {
    execFileSync("apt-get", ["install", "-s", "-y", ...deps], { stdio: "pipe" });
    return deps;
  } catch {
    return deps.map((dep) =>
      aptInstallable(dep) ? dep : aptInstallable(`${dep}t64`) ? `${dep}t64` : dep
    );
  }
}

/** Run a privileged package-manager command.
 *
 * Prefer bare invocation when already root (Docker/CI images rarely ship
 * sudo). Fall back to sudo for unprivileged interactive installs.
 */
function runAsRoot(argv: string[]): void {
  if (typeof process.getuid === "function" && process.getuid() === 0) {
    execFileSync(argv[0], argv.slice(1), { stdio: "inherit" });
    return;
  }
  execFileSync("sudo", argv, { stdio: "inherit" });
}

function installSystemDeps(): void {
  if (os.platform() !== "linux") {
    process.stderr.write("[camoufox-cli] System dependencies are only needed on Linux, skipping.\n");
    return;
  }

  process.stderr.write("[camoufox-cli] Installing system dependencies...\n");

  if (fs.existsSync("/usr/bin/apt-get")) {
    runAsRoot(["apt-get", "update", "-y"]);
    // Resolve AFTER update: dry-run resolution needs a populated apt cache.
    const deps = resolveAptDeps(APT_DEPS);
    runAsRoot(["apt-get", "install", "-y", ...deps]);
  } else if (fs.existsSync("/usr/bin/dnf")) {
    runAsRoot(["dnf", "install", "-y", ...DNF_DEPS]);
  } else if (fs.existsSync("/usr/bin/yum")) {
    runAsRoot(["yum", "install", "-y", ...YUM_DEPS]);
  } else {
    process.stderr.write("[camoufox-cli] Could not detect a supported package manager (apt-get, dnf, yum).\n");
    process.exit(1);
  }

  process.stderr.write("[camoufox-cli] System dependencies installed.\n");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  // Preflight before anything touches camoufox-js: its dependency chain uses
  // JSON import attributes (`with { type: "json" }`), which need Node 20.10+.
  // Without this check, older Nodes die with a bare SyntaxError deep inside
  // node_modules (or a silently failing daemon) instead of a usable message.
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (major < 20 || (major === 20 && minor < 10)) {
    process.stderr.write(
      `Error: camoufox-cli requires Node.js 20.10 or newer (found ${process.versions.node}).\n`
    );
    process.exit(1);
  }

  const argv = process.argv.slice(2);

  // Short-circuit before parseArgs: --version has no command and needs no daemon.
  if (argv.includes("--version")) {
    console.log(getVersion());
    return;
  }

  const { flags, command } = parseArgs(argv);

  // Resolve default persistent path
  if (flags.persistent === "") {
    flags.persistent = path.join(os.homedir(), ".camoufox-cli", "profiles", flags.session);
  }

  const action = command.action as string;

  // Client-side: install
  if (action === "install") {
    process.stderr.write("[camoufox-cli] Downloading browser...\n");
    const { installBrowser } = await import("./install.js");
    await installBrowser();
    process.stderr.write("[camoufox-cli] Browser installed.\n");
    if ((command.params as any)?.with_deps) {
      installSystemDeps();
    }
    return;
  }

  // Client-side: sessions
  if (action === "sessions") {
    const sessions = listSessions();
    if (flags.json) {
      console.log(JSON.stringify(sessions, null, 2));
    } else if (sessions.length === 0) {
      console.log("No active sessions.");
    } else {
      sessions.forEach((s) => console.log(s));
    }
    return;
  }

  // Client-side: close --all
  if (action === "close" && (command.params as any)?.all) {
    const sessions = listSessions();
    if (sessions.length === 0) { console.log("No active sessions."); return; }
    // Force: tear each session's browser down regardless of open tabs.
    const closeCmd = { id: "r1", action: "close", params: { force: true } };
    for (const session of sessions) {
      try { await sendCommand(getSocketPath(session), closeCmd); }
      catch (e: any) { process.stderr.write(`Failed to close session ${session}: ${e.message}\n`); }
    }
    return;
  }

  // Ensure daemon is running
  await ensureDaemon(flags.session, flags.headed, flags.timeout, flags.persistent, flags.proxy, flags.geoip, flags.locale);

  const sockPath = getSocketPath(flags.session);

  // Send command with retry
  let lastErr = "";
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const response = await sendCommand(sockPath, command);
      printResponse(response, flags.json);
      return;
    } catch (e: any) {
      lastErr = e.message || String(e);
      // close is idempotent: if the daemon is gone (socket removed), there is
      // nothing left to close — that IS success. This is the receipt for a
      // close that raced the last-tab shutdown: the daemon may exit after
      // releasing our tab but before our response could be delivered.
      if (action === "close" && !fs.existsSync(sockPath)) {
        if (flags.json) console.log(JSON.stringify({ id: "r1", success: true, data: { closed: true } }));
        return;
      }
      if (attempt < 4) await new Promise((r) => setTimeout(r, 200 * (attempt + 1)));
    }
  }

  // Same idempotent-close check once more: the daemon may have finished
  // unlinking its socket only while we were burning the retry budget.
  if (action === "close" && !fs.existsSync(sockPath)) {
    if (flags.json) console.log(JSON.stringify({ id: "r1", success: true, data: { closed: true } }));
    return;
  }
  process.stderr.write(`Error: Failed to connect to daemon after 5 attempts: ${lastErr}\n`);
  process.exit(1);
}

const USAGE = `Usage: camoufox-cli [flags] <command> [args]

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
  --persistent [path]  Persistent identity — freeze fingerprint/OS/locale + store cookies/state (default: ~/.camoufox-cli/profiles/<session>)
  --proxy <url>        Proxy server (e.g. http://host:port or https://host:443)
  --no-geoip           Disable automatic GeoIP spoofing (auto-enabled with --proxy)
  --locale <tag>       Force browser locale (e.g. "en-US" or "en-US,zh-CN")
  --version            Print version and exit

Config file:
  ~/.camoufox-cli/config.json sets defaults for the flags above (override the
  path with $CAMOUFOX_CLI_CONFIG). Command-line flags always take precedence.
  Use a "default" block plus optional per-session blocks under "sessions".`;

const isDirectRun = (() => {
  try {
    return process.argv[1] &&
      fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url);
  } catch { return false; }
})();
if (isDirectRun) main();
