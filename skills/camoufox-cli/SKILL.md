---
name: camoufox-cli
description: Anti-detect browser automation CLI & Skills for AI agents. Use when the user needs to interact with websites with bot detection, CAPTCHAs, or anti-bot blocks, including navigating pages, filling forms, clicking buttons, taking screenshots, extracting data, testing web apps, or automating any browser task that requires bypassing fingerprint checks.
---

# Anti-Detect Browser Automation with camoufox-cli

## What Makes This Different

camoufox-cli is built on Camoufox (anti-detect Firefox) with C++-level fingerprint spoofing:
- `navigator.webdriver` = `false`
- Real browser plugins, randomized canvas/WebGL/audio fingerprints
- Real Firefox UA string -- passes bot detection on sites that block Chromium automation

Use camoufox-cli instead of agent-browser when the target site has bot detection.

## Core Workflow

Every browser automation follows this pattern:

1. **Navigate**: `camoufox-cli open <url>`
2. **Snapshot**: `camoufox-cli snapshot -i` (get element refs like `@e1`, `@e2`)
3. **Interact**: Use refs to click, fill, select
4. **Re-snapshot**: After navigation or DOM changes, get fresh refs
5. **Close**: `camoufox-cli close` (close the browser when the entire task is fully complete; keep it open if the user may have follow-up instructions)

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
camoufox-cli close                   # Close browser and stop daemon
camoufox-cli close --all             # Close all sessions

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
camoufox-cli tabs                    # List open tabs
camoufox-cli switch 2                # Switch to tab by index
camoufox-cli close-tab               # Close current tab

# Cookies & State
camoufox-cli cookies                 # Dump cookies as JSON
camoufox-cli cookies import file.json # Import cookies
camoufox-cli cookies export file.json # Export cookies

# Sessions
camoufox-cli sessions                # List active sessions
camoufox-cli --session work open <url> # Use named session
camoufox-cli close --all             # Close all sessions

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

### Multiple Tabs

```bash
camoufox-cli open https://site-a.com
camoufox-cli eval "window.open('https://site-b.com')"
camoufox-cli tabs                    # List tabs
camoufox-cli switch 1                # Switch to second tab
camoufox-cli snapshot -i
```

### Parallel Sessions

```bash
camoufox-cli --session s1 open https://site-a.com
camoufox-cli --session s2 open https://site-b.com
camoufox-cli sessions                # List both
camoufox-cli --session s1 snapshot -i
camoufox-cli --session s2 snapshot -i
```

### Visual Browser (Debugging)

```bash
camoufox-cli --headed open https://example.com
camoufox-cli snapshot -i
camoufox-cli screenshot debug.png
```

## Session Management and Cleanup

When running multiple agents or automations concurrently, always use named sessions to avoid conflicts:

```bash
camoufox-cli --session agent1 open https://site-a.com
camoufox-cli --session agent2 open https://site-b.com
camoufox-cli sessions                  # Check active sessions
```

Always close your browser session when done to avoid leaked processes:

```bash
camoufox-cli close                     # Close default session
camoufox-cli --session agent1 close    # Close specific session
camoufox-cli close --all               # Close all sessions
```

If a previous session was not closed properly, the daemon may still be running. Use `camoufox-cli close` to clean it up before starting new work.

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
--headed               Show browser window (default: headless)
--timeout <seconds>    Daemon idle timeout (default: 1800)
--json                 Output as JSON instead of human-readable
--persistent [path]    Use persistent browser profile (default: ~/.camoufox-cli/profiles/<session>)
--proxy <url>          Proxy server (e.g. http://host:port or http://user:pass@host:port)
```

## Documentation

- [camoufox-cli documentation](https://github.com/Bin-Huang/camoufox-cli) -- Full README, setup guide, installation, and command reference
