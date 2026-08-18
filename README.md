# camoufox-cli

Anti-detect browser CLI & Skills for AI agents, powered by [Camoufox](https://github.com/daijro/camoufox).

### Highlights

- C++-level fingerprint spoofing via Camoufox (canvas, WebGL, audio, screen metrics, fonts)
- Persistent identities: stable fingerprint, OS, and locale across launches with `--persistent`
- Accessibility-tree snapshots with `@ref` element targeting
- Session isolation with cookie import/export
- Shell commands, no code generation

## Sponsors

<table>
<tr>
<td align="center">
<a href="https://www.swiftproxy.net/?ref=bin" target="_blank"><img src="./doc//assets/swiftproxy.png" width="300" alt="Swiftproxy logo" /></a>
<br />
<small>Swiftproxy - Get 90M+ Clean Residential Proxies provides high-quality residential and static residential proxies designed for Anti-Bot protection, risk control, and multi-account isolation.</small>
</td>
</tr>
</table>

### Works with

OpenClaw, Claude Code, Cursor, Codex, and any agent that can run shell commands.

## Install

Tell your AI agent (e.g. OpenClaw):

> Install this CLI and skills from https://github.com/Bin-Huang/camoufox-cli

Or install manually:

```bash
npm install -g camoufox-cli      # Requires Node.js 20.10+
camoufox-cli install              # Download browser
```

Or with pip:

```bash
pipx install camoufox-cli
camoufox-cli install              # Download browser
```

On Linux, install system dependencies with:

```bash
camoufox-cli install --with-deps
```

The browser is downloaded from GitHub releases. If the anonymous GitHub API
rate limit is exhausted (common on shared server/CI IPs), the installer
automatically falls back to scraping github.com release pages.

### Agent Skill

```bash
# Add skills for AI agents (Claude Code, Cursor, Codex, etc.)
npx skills add Bin-Huang/camoufox-cli
```

## Quick Start

```bash
camoufox-cli open https://example.com    # Launch browser & navigate
camoufox-cli snapshot -i                  # Interactive elements only
# - link "More information..." [ref=e1]
camoufox-cli click @e1                    # Click by ref
camoufox-cli close                        # Done
```

## Commands

### Navigation

```bash
camoufox-cli open <url>                   # Navigate to URL (starts daemon if needed)
camoufox-cli back                         # Go back
camoufox-cli forward                      # Go forward
camoufox-cli reload                       # Reload page
camoufox-cli url                          # Print current URL
camoufox-cli title                        # Print page title
camoufox-cli close                        # Close your tab (browser exits when the last tab closes)
```

### Snapshot

```bash
camoufox-cli snapshot                     # Full accessibility tree
camoufox-cli snapshot -i                  # Interactive elements only
camoufox-cli snapshot -s "css-selector"   # Scoped to CSS selector
```

Output format:

```
- heading "Example Domain" [level=1] [ref=e1]
- paragraph [ref=e2]
  - link "More information..." [ref=e3]
```

### Interaction

```bash
camoufox-cli click @e1                    # Click element
camoufox-cli fill @e3 "search query"      # Clear + type into input
camoufox-cli type @e3 "append text"       # Type without clearing
camoufox-cli select @e5 "option text"     # Select dropdown option
camoufox-cli check @e6                    # Toggle checkbox
camoufox-cli hover @e2                    # Hover over element
camoufox-cli press Enter                  # Press keyboard key
camoufox-cli press "Control+a"            # Key combination
```

### Data Extraction

```bash
camoufox-cli text @e1                     # Get text content of element
camoufox-cli text body                    # Get all page text
camoufox-cli eval "document.title"        # Execute JavaScript
camoufox-cli screenshot                   # Screenshot (JSON with base64)
camoufox-cli screenshot page.png          # Screenshot to file
camoufox-cli screenshot --full page.png   # Full page screenshot
```

### Scroll & Wait

```bash
camoufox-cli scroll down                  # Scroll down 500px
camoufox-cli scroll up 1000               # Scroll up 1000px
camoufox-cli wait 2000                    # Wait milliseconds
camoufox-cli wait @e1                     # Wait for element to appear
camoufox-cli wait --url "*/dashboard"     # Wait for URL pattern
```

### Tabs

```bash
camoufox-cli tabs                         # List open tabs (with owner names)
camoufox-cli switch 2                     # Switch to tab by index
```

Named tabs let concurrent agents share one browser — same fingerprint, same cookies/login state — while each keeps its own page, element refs, and history. Tabs share one browser process (commands from different tabs may queue behind a slow one); separate sessions run as independent processes in parallel:

```bash
camoufox-cli --tab inbox-scan-x4q open https://app.example.com/a
camoufox-cli --tab report-pull-9kf open https://app.example.com/b
camoufox-cli --tab inbox-scan-x4q snapshot -i   # refs are per tab
camoufox-cli --tab inbox-scan-x4q close         # frees only this tab; browser exits when the last tab closes
```

Tab names must be unique per agent (nothing enforces this): use a task slug plus a short shell-generated random suffix (e.g. `price-scan-$(openssl rand -hex 2)`), chosen once and reused.

### Sessions

Each named session is a separate browser process with its own randomly-generated fingerprint and its own cookies. Use sessions for isolated identities, named tabs (above) for cheap parallelism under one identity. For real multi-account isolation, combine sessions with a per-session proxy (config file) and `--persistent` — see Persistent Identity below:

```bash
camoufox-cli sessions                     # List active sessions
camoufox-cli --session work open <url>    # Use named session
camoufox-cli close --all                  # Force-close all sessions
```

### Cookies

```bash
camoufox-cli cookies                      # Dump cookies as JSON
camoufox-cli cookies import file.json     # Import cookies
camoufox-cli cookies export file.json     # Export cookies
```

## Flags

```
--session <name>       Named session (default: "default")
--tab <name>           Named tab within the session's shared browser: same fingerprint and
                       cookies/login, independent page/refs/history (default: "default")
--headed               Show browser window (default: headless)
--timeout <seconds>    Daemon idle timeout (default: 1800)
--json                 Output as JSON
--persistent [path]    Persistent identity (see below); default path: ~/.camoufox-cli/profiles/<session>
--proxy <url>          Proxy server (http:// or https://; auth: http://user:pass@host:port)
--no-geoip             Disable automatic GeoIP spoofing (auto-enabled with --proxy)
--locale <tag>         Force browser locale (e.g. "en-US" or "en-US,zh-CN")
--version              Print version and exit
```

## Config File

Tired of repeating the same flags on every call? Put defaults in `~/.camoufox-cli/config.json` (override the path with `$CAMOUFOX_CLI_CONFIG`):

```json
{
  "default": {
    "persistent": true,
    "timeout": 3600,
    "proxy": "http://user:pass@host:8080"
  },
  "sessions": {
    "<your-session-name>": {
      "proxy": "socks5://127.0.0.1:1080",
      "locale": "zh-CN"
    }
  }
}
```

- **`default`** applies to every session.
- **`sessions` is optional.** You never pre-register sessions — the name is just whatever you pass to `--session`. A `sessions.<name>` block only kicks in when you happen to run `--session <name>`, layering its keys on top of `default`; any other session (or no `--session` at all) just uses `default`. Above, `camoufox-cli --session <your-session-name> open <url>` swaps in that block's proxy + locale, while every other session keeps the `default` proxy.
- **Command-line flags always win** over the file, which in turn wins over built-in defaults.
- Settable keys: `proxy`, `locale`, `geoip`, `persistent` (`true` / `false` / path string), `headed`, `timeout`, `json`. `session` is command-line only (it selects which block to apply), and per-command options like `--full` or `-i` are never read from config.
- A broken config never blocks a command — it's ignored with a warning on stderr.
- Config is read when a session's daemon **first launches**. If one is already running for that session, run `camoufox-cli --session <name> close` first for changes to take effect.

## Persistent Identity

Without `--persistent`, every launch gets a fresh random fingerprint. With `--persistent`, a `camoufox-cli.json` file is written next to the browser's user data. Fingerprint, OS, and canvas/font seeds are generated on the first launch and frozen afterwards; locale and proxy-derived timezone/geolocation are also saved but track whatever you pass on the command line. Every subsequent launch with the same path reloads the identity, so sites see the same device on every visit.

```bash
# First launch: generates + stores identity
camoufox-cli --persistent ~/.camoufox-cli/profiles/alice open https://example.com

# Every subsequent launch: same fingerprint, same cookies, same device
camoufox-cli --persistent ~/.camoufox-cli/profiles/alice open https://example.com
```

**Frozen** — generated on the first launch, permanent until the directory is deleted:

- Fingerprint (UA, canvas, WebGL, fonts, navigator properties)
- OS (defaults to host OS)
- Canvas/font noise seeds

**Persisted** — stored in the file, refreshed whenever you pass the flag:

- `--locale`: sets the stored locale; pass it again to change it, omit it to keep the stored value.
- Timezone / geolocation: re-derived from the current proxy's IP whenever `--proxy` is active (and `--no-geoip` isn't set), then written back. Without a proxy, the last stored values stay in effect.

**Per-launch** — never stored; pass on every launch for it to apply:

- `--proxy`: proxies rotate or expire; re-specify each launch to avoid silently running through a stale one.
- `--no-geoip`: follows the current `--proxy`.

**Multiple identities in parallel.** Each persistent path is a distinct identity. Combine with `--session` for concurrent daemons:

```bash
camoufox-cli --session a --persistent ~/.camoufox-cli/profiles/alice open https://...
camoufox-cli --session b --persistent ~/.camoufox-cli/profiles/bob   open https://...
```

**Resetting an identity.** Just delete the directory (`rm -rf ~/.camoufox-cli/profiles/alice`). The next launch generates a fresh one.

## Architecture

```
CLI (camoufox-cli)  ──Unix socket──▶  Daemon (Python)  ──Playwright──▶  Camoufox (Firefox)
```

The CLI sends JSON commands to a long-running daemon process via Unix socket. The daemon manages the Camoufox browser instance and maintains the ref registry between commands. The daemon auto-starts on the first command and auto-stops after 30 minutes of inactivity.

## Related

- [google-analytics-cli](https://github.com/Bin-Huang/google-analytics-cli) -- Google Analytics CLI & Skills for AI agents (and humans)
- [google-search-console-cli](https://github.com/Bin-Huang/google-search-console-cli) -- Google Search Console CLI & Skills for AI agents (and humans)
- [youtube-analytics-cli](https://github.com/Bin-Huang/youtube-analytics-cli) -- YouTube Analytics CLI & Skills for AI agents (and humans)
- [x-analytics-cli](https://github.com/Bin-Huang/x-analytics-cli) -- X Analytics CLI & Skills for AI agents (and humans)
- [google-ads-open-cli](https://github.com/Bin-Huang/google-ads-open-cli) -- Google Ads CLI & Skills for AI agents (and humans)
- [meta-ads-open-cli](https://github.com/Bin-Huang/meta-ads-open-cli) -- Meta Ads CLI & Skills for AI agents (and humans)
- [microsoft-ads-cli](https://github.com/Bin-Huang/microsoft-ads-cli) -- Microsoft Ads CLI & Skills for AI agents (and humans)
- [amazon-ads-open-cli](https://github.com/Bin-Huang/amazon-ads-open-cli) -- Amazon Ads CLI & Skills for AI agents (and humans)
- [tiktok-ads-cli](https://github.com/Bin-Huang/tiktok-ads-cli) -- TikTok Ads CLI & Skills for AI agents (and humans)
- [linkedin-ads-cli](https://github.com/Bin-Huang/linkedin-ads-cli) -- LinkedIn Ads CLI & Skills for AI agents (and humans)
- [x-ads-cli](https://github.com/Bin-Huang/x-ads-cli) -- X Ads CLI & Skills for AI agents (and humans)
- [snapchat-ads-cli](https://github.com/Bin-Huang/snapchat-ads-cli) -- Snapchat Ads CLI & Skills for AI agents (and humans)
- [pinterest-ads-cli](https://github.com/Bin-Huang/pinterest-ads-cli) -- Pinterest Ads CLI & Skills for AI agents (and humans)
- [reddit-ads-cli](https://github.com/Bin-Huang/reddit-ads-cli) -- Reddit Ads CLI & Skills for AI agents (and humans)
- [spotify-ads-cli](https://github.com/Bin-Huang/spotify-ads-cli) -- Spotify Ads CLI & Skills for AI agents (and humans)
- [apple-ads-cli](https://github.com/Bin-Huang/apple-ads-cli) -- Apple Ads CLI & Skills for AI agents (and humans)

## License

MIT
