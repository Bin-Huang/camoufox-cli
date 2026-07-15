---
name: camoufox-cli
description: Anti-detect browser automation CLI & Skills for AI agents. Use when the user needs to interact with websites with bot detection, CAPTCHAs, or anti-bot blocks, including navigating pages, filling forms, clicking buttons, taking screenshots, extracting data, testing web apps, or automating any browser task that requires bypassing fingerprint checks.
---

# Anti-Detect Browser Automation with camoufox-cli

## Core Workflow

Every browser automation follows this pattern:

1. **Navigate**: `camoufox-cli open <url>`
2. **Snapshot**: `camoufox-cli snapshot -i` (get element refs like `@e1`, `@e2`)
3. **Interact**: Use refs to click, fill, select
4. **Re-snapshot**: After navigation or DOM changes, get fresh refs
5. **Close**: `camoufox-cli close` when the entire task is complete — with the same `--tab`/`--session` flags as your other commands. Keep it open if the user may have follow-up instructions.

```bash
camoufox-cli open https://example.com/form
camoufox-cli snapshot -i
# Output: - textbox "Email" [ref=e1]
#         - textbox "Password" [ref=e2]
#         - button "Submit" [ref=e3]

camoufox-cli fill @e1 "user@example.com"
camoufox-cli fill @e2 "password123"
camoufox-cli click @e3
camoufox-cli snapshot -i  # Check result
```

## Command Chaining

Commands can be chained with `&&` in a single shell invocation. The browser persists between commands via a background daemon, so chaining is safe and more efficient than separate calls.

```bash
# Chain open + snapshot in one call
camoufox-cli open https://example.com && camoufox-cli snapshot -i

# Chain multiple interactions
camoufox-cli fill @e1 "user@example.com" && camoufox-cli fill @e2 "password123" && camoufox-cli click @e3

# Navigate and capture
camoufox-cli open https://example.com && camoufox-cli screenshot page.png
```

**When to chain:** Use `&&` when you don't need to read the output of an intermediate command before proceeding (e.g., open + screenshot). Run commands separately when you need to parse the output first (e.g., snapshot to discover refs, then interact using those refs).

## Essential Commands

```bash
# Navigation
camoufox-cli open <url>              # Navigate to URL (starts daemon if needed)
camoufox-cli back                    # Go back
camoufox-cli forward                 # Go forward
camoufox-cli reload                  # Reload page
camoufox-cli url                     # Print current URL
camoufox-cli title                   # Print page title
camoufox-cli close                   # Close your tab (browser exits when the last tab closes)
camoufox-cli close --all             # Force-close all sessions

# Snapshot
camoufox-cli snapshot                # Full aria tree of page
camoufox-cli snapshot -i             # Interactive elements only (recommended)
camoufox-cli snapshot -s "#selector" # Scope to CSS selector

# Interaction (use @refs from snapshot)
camoufox-cli click @e1               # Click element
camoufox-cli fill @e1 "text"         # Clear + type into input
camoufox-cli type @e1 "text"         # Type without clearing (append)
camoufox-cli select @e1 "option"     # Select dropdown option
camoufox-cli check @e1               # Toggle checkbox
camoufox-cli hover @e1               # Hover over element
camoufox-cli press Enter             # Press keyboard key
camoufox-cli press "Control+a"       # Key combination

# Data Extraction
camoufox-cli text @e1                # Get text content of element
camoufox-cli text body               # Get all page text (CSS selector)
camoufox-cli eval "document.title"   # Execute JavaScript

# Capture
camoufox-cli screenshot              # Screenshot as JSON {"base64": "..."}
camoufox-cli screenshot page.png     # Screenshot to file
camoufox-cli screenshot --full p.png # Full page screenshot
camoufox-cli pdf output.pdf          # Save page as PDF

# Scroll & Wait
camoufox-cli scroll down             # Scroll down 500px
camoufox-cli scroll up               # Scroll up 500px
camoufox-cli scroll down 1000        # Scroll down 1000px
camoufox-cli wait @e1                # Wait for element to appear
camoufox-cli wait 2000               # Wait milliseconds
camoufox-cli wait --url "*/dashboard" # Wait for URL pattern

# Tabs
camoufox-cli tabs                    # List open tabs (with owner names)
camoufox-cli switch 2                # Switch to tab by index
camoufox-cli --tab <unique-name> open <url> # Named tab: shared browser + login, own page/refs

# Cookies & State
camoufox-cli cookies                 # Dump cookies as JSON
camoufox-cli cookies import file.json # Import cookies
camoufox-cli cookies export file.json # Export cookies

# Sessions
camoufox-cli sessions                # List active sessions
camoufox-cli --session work open <url> # Use named session
camoufox-cli close --all             # Force-close all sessions

# Setup
camoufox-cli install                 # Download Camoufox browser
camoufox-cli install --with-deps     # Download browser + system libs (Linux)
```

## Common Patterns

### Form Submission

```bash
camoufox-cli open https://example.com/signup
camoufox-cli snapshot -i
camoufox-cli fill @e1 "Jane Doe"
camoufox-cli fill @e2 "jane@example.com"
camoufox-cli select @e3 "California"
camoufox-cli check @e4
camoufox-cli click @e5
camoufox-cli snapshot -i  # Verify submission result
```

### Data Extraction

```bash
camoufox-cli open https://example.com/products
camoufox-cli snapshot -i
camoufox-cli text @e5                # Get specific element text
camoufox-cli eval "document.title"   # Get page title via JS
camoufox-cli screenshot results.png  # Visual capture
```

### Cookie Management (Persist Login)

```bash
# Login and export cookies
camoufox-cli open https://app.example.com/login
camoufox-cli snapshot -i
camoufox-cli fill @e1 "user"
camoufox-cli fill @e2 "pass"
camoufox-cli click @e3
camoufox-cli cookies export auth.json

# Restore in future session
camoufox-cli open https://app.example.com
camoufox-cli cookies import auth.json
camoufox-cli reload
```

For long-lived accounts where the site also verifies device stability (not just the cookie), combine this with `--persistent` so the fingerprint stays fixed alongside the cookies — see the Persistent Identity section below.

### Multiple Tabs

```bash
camoufox-cli open https://site-a.com
camoufox-cli eval "window.open('https://site-b.com')"
camoufox-cli tabs                    # List tabs
camoufox-cli switch 1                # Switch to second tab
camoufox-cli snapshot -i
```

### Parallel Tabs (shared identity, one browser)

Named tabs share one browser within a session — same fingerprint, same cookies/login state — but each tab keeps its own page, element refs, and navigation history, so concurrent agents never clobber each other. This is the cheap way to parallelize: one Firefox total, roughly 50-150MB per extra tab.

```bash
camoufox-cli --tab inbox-scan-x4q open https://app.example.com/inbox
camoufox-cli --tab report-pull-9kf open https://app.example.com/reports
camoufox-cli --tab inbox-scan-x4q snapshot -i   # refs are per tab
camoufox-cli tabs                               # Lists every tab with its owner name
camoufox-cli --tab inbox-scan-x4q close         # Frees only this tab; browser stays for the others
```

**Picking your tab name.** Nothing enforces uniqueness — two agents using the same name share one page pointer and will clobber each other. Generate your name ONCE at the start of your task: a short slug of *your specific task* plus a shell-generated random suffix — don't invent the suffix yourself, LLM-"random" characters are biased and concurrent agents may produce the same ones. Then reuse the printed name verbatim in every subsequent command. (If your instructions explicitly assign you a tab name, use that instead.)

```bash
TAB="price-scan-$(openssl rand -hex 2)" && echo "$TAB" && camoufox-cli --tab "$TAB" open https://example.com
# prints e.g. price-scan-9f3c — use that exact name in every later command:
camoufox-cli --tab price-scan-9f3c snapshot -i
```

Use tabs when subagents should act as the same identity (e.g. all operating the same logged-in account). Cleanup needs no coordination: every agent runs `close` when done, addressed to its own tab (`camoufox-cli --tab <name> close`) — it releases only that tab, and the browser exits by itself when the last tab closes.

Tabs share one browser process, so commands from different tabs may queue behind a slow navigation or `wait`; separate sessions run as independent processes and execute fully in parallel. If a few agents are extremely command-heavy, consider giving those their own session and keeping the rest on tabs.

### Parallel Sessions (isolated identities)

Each named session is a separate browser process, so each gets its own randomly-generated fingerprint and its own cookies. Use this when agents must NOT share identity (multi-account work) — it costs a full Firefox (~300-500MB) per session:

```bash
camoufox-cli --session s1 open https://site-a.com
camoufox-cli --session s2 open https://site-b.com
camoufox-cli sessions                # List both
camoufox-cli --session s1 snapshot -i
camoufox-cli --session s2 snapshot -i
```

Separate sessions alone only isolate the browser side. For multi-account work that must survive scrutiny, also give each session its own proxy (sites correlate accounts by IP — use the config file's `sessions.<name>.proxy`) and `--persistent` (otherwise the fingerprint is re-randomized every launch, which looks like a new device on each login).

### Visual Browser (Debugging)

```bash
camoufox-cli --headed open https://example.com
camoufox-cli snapshot -i
camoufox-cli screenshot debug.png
```

## Session Management and Cleanup

When running multiple agents or automations concurrently, give each agent its own name so they don't conflict. Two isolation levels:

- **`--tab <name>`** (shared identity, recommended default): all agents share one browser — same fingerprint and login state — but each gets an independent tab. Cheap: one Firefox total.
- **`--session <name>`** (isolated identity): each agent gets its own browser with its own fingerprint and cookies. Expensive: a full Firefox per session. Use only when identities must be separate.

```bash
# Shared identity: 3 agents, one browser, one login
camoufox-cli --tab orders-audit-p2m open https://app.example.com/a
camoufox-cli --tab user-export-j8w open https://app.example.com/b
camoufox-cli --tab billing-check-r4t open https://app.example.com/c

# Isolated identities: 2 agents, two browsers
camoufox-cli --session shop-a-buyer open https://site-a.com
camoufox-cli --session shop-b-buyer open https://site-b.com
camoufox-cli sessions                  # Check active sessions
```

Names are just strings and nothing enforces uniqueness — follow the "Picking your tab name" rule above (task slug + shell-generated random suffix, chosen once). The same applies to session names.

Always run `close` when done to avoid leaked processes — with the same `--tab`/`--session` flags as your other commands, since `close` releases the tab the command is addressed to. The browser exits when the last tab closes, so every agent cleans up the same way without knowing about the others:

```bash
camoufox-cli --tab orders-audit-p2m close       # Free this tab; browser exits if it was the last
camoufox-cli close                              # Same, for the default tab
camoufox-cli --session shop-a-buyer close       # Same, within a named session
camoufox-cli close --all                        # Force-close all sessions (cleanup escape hatch)
```

If a previous session was not closed properly, the daemon may still be running. Use `camoufox-cli close` (or `close --all`) to clean it up before starting new work.

## Timeouts and Slow Pages

Some pages take time to fully load, especially those with dynamic content or heavy JavaScript. Use explicit waits before taking a snapshot:

```bash
# Wait for a specific element to appear
camoufox-cli wait @e1
camoufox-cli snapshot -i

# Wait for a URL pattern (useful after redirects)
camoufox-cli wait --url "*/dashboard"
camoufox-cli snapshot -i

# Wait a fixed duration as a last resort
camoufox-cli wait 3000
camoufox-cli snapshot -i
```

When dealing with slow pages, always wait before snapshotting. If you snapshot too early, elements may be missing from the output.

## Ref Lifecycle (Important)

Refs (`@e1`, `@e2`, etc.) are **temporary identifiers** assigned by sequential numbering during each snapshot. They are invalidated when the page changes.

**Always re-snapshot after:**

- Clicking links or buttons that navigate
- Form submissions
- Dynamic content loading (dropdowns, modals, lazy-loaded content)
- Scrolling that triggers new content

```bash
# CORRECT: re-snapshot after navigation
camoufox-cli click @e5              # Navigates to new page
camoufox-cli snapshot -i            # MUST re-snapshot
camoufox-cli click @e1              # Use new refs

# CORRECT: re-snapshot after dynamic changes
camoufox-cli click @e1              # Opens dropdown
camoufox-cli snapshot -i            # See dropdown items
camoufox-cli click @e7              # Select item

# WRONG: using refs without snapshot
camoufox-cli open https://example.com
camoufox-cli click @e1              # Ref doesn't exist yet!

# WRONG: using old refs after navigation
camoufox-cli click @e5              # Navigates away
camoufox-cli click @e3              # STALE REF - wrong element!
```

Always take a fresh snapshot before interacting with elements after navigation or page changes.

## Troubleshooting

### "Ref @eN not found"

The ref was invalidated. Re-snapshot to get fresh refs:

```bash
camoufox-cli snapshot -i
```

### Element Not Visible in Snapshot

```bash
# Scroll down to reveal element
camoufox-cli scroll down 1000
camoufox-cli snapshot -i

# Or wait for dynamic content
camoufox-cli wait 2000
camoufox-cli snapshot -i
```

### Too Many Elements in Snapshot

```bash
# Scope to a specific container
camoufox-cli snapshot -s "#main-content"
camoufox-cli snapshot -i -s "form.login"
```

### Page Not Fully Loaded

```bash
# Wait for URL pattern after redirect
camoufox-cli wait --url "*/dashboard"
camoufox-cli snapshot -i

# Wait a fixed duration as last resort
camoufox-cli wait 3000
camoufox-cli snapshot -i
```

## Global Flags

```
--session <name>       Named session (default: "default")
--tab <name>           Named tab within the session's shared browser: same
                       fingerprint and cookies/login, independent page/refs/
                       history (default: "default")
--headed               Show browser window (default: headless)
--timeout <seconds>    Daemon idle timeout (default: 1800)
--json                 Output as JSON instead of human-readable
--persistent [path]    Persistent identity — reuse the same fingerprint + cookies across launches
                       (default path: ~/.camoufox-cli/profiles/<session>)
--proxy <url>          Proxy server (http:// or https://; auth: http://user:pass@host:port)
--no-geoip             Disable automatic GeoIP spoofing (auto-enabled with --proxy)
--locale <tag>         Force browser locale (e.g. "en-US" or "en-US,zh-CN")
--version              Print version and exit
```

**Config file (optional).** To avoid repeating flags, set defaults in `~/.camoufox-cli/config.json` (override path with `$CAMOUFOX_CLI_CONFIG`): a `default` block applies to all sessions, and an optional `sessions.<name>` block layers extra overrides on top whenever you run `--session <name>` (the name is just whatever you pass to `--session` — sessions are never pre-registered). Settable keys: `proxy`, `locale`, `geoip`, `persistent` (`true`/`false`/path), `headed`, `timeout`, `json`. Command-line flags always win over the file. Config is read only when a session's daemon first launches.

```json
{
  "default": { "persistent": true, "timeout": 3600 },
  "sessions": { "<your-session-name>": { "proxy": "socks5://127.0.0.1:1080", "locale": "zh-CN" } }
}
```

## Persistent Identity

By default, every launch gets a fresh random fingerprint. Add `--persistent [path]` to reuse the same fingerprint + cookies across launches — fingerprint/OS/canvas+font seeds are frozen on first launch (delete the directory to reset); `--locale` and proxy-derived timezone/geolocation are stored but refreshed whenever you pass the flag; `--proxy` / `--no-geoip` are never stored, so pass them every launch.

**Use it when** the same device should see the same fingerprint across visits (account-bound tasks, parallel independent identities, or when `cookies import/export` alone isn't enough because the site also checks device stability). **Skip it** for one-off scraping or quick debugging.

```bash
# Parallel identities, each with its own fingerprint + cookies
camoufox-cli --session a --persistent ~/.camoufox-cli/profiles/alice open https://app.example.com
camoufox-cli --session b --persistent ~/.camoufox-cli/profiles/bob   open https://app.example.com

# Reset an identity: just remove the directory
rm -rf ~/.camoufox-cli/profiles/alice
```

## Documentation

- [camoufox-cli documentation](https://github.com/Bin-Huang/camoufox-cli) -- Full README, setup guide, installation, and command reference
