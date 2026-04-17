# Command Reference

Complete reference for all camoufox-cli commands. For quick start and common patterns, see SKILL.md.

## Navigation

```bash
camoufox-cli open <url>              # Navigate to URL (starts daemon if needed)
                                     # Auto-prepends https:// if no protocol given
camoufox-cli back                    # Go back
camoufox-cli forward                 # Go forward
camoufox-cli reload                  # Reload page
camoufox-cli url                     # Print current URL
camoufox-cli title                   # Print page title
camoufox-cli close                   # Close browser and stop daemon
camoufox-cli close --all             # Close all sessions
```

## Snapshot (Page Analysis)

```bash
camoufox-cli snapshot                # Full accessibility tree
camoufox-cli snapshot -i             # Interactive elements only (recommended)
camoufox-cli snapshot -s "#main"     # Scope to CSS selector
camoufox-cli snapshot -i -s "form"   # Interactive + scoped
```

## Interactions (use @refs from snapshot)

```bash
camoufox-cli click @e1               # Click element
camoufox-cli fill @e1 "text"         # Clear and type
camoufox-cli type @e1 "text"         # Type without clearing (append)
camoufox-cli select @e1 "value"      # Select dropdown option
camoufox-cli check @e1               # Toggle checkbox
camoufox-cli hover @e1               # Hover over element
camoufox-cli press Enter             # Press key
camoufox-cli press "Control+a"       # Key combination
```

## Get Information

```bash
camoufox-cli text @e1                # Get element text (by ref)
camoufox-cli text body               # Get all page text (by CSS selector)
camoufox-cli url                     # Get current URL
camoufox-cli title                   # Get page title
camoufox-cli eval "document.title"   # Run JavaScript expression
```

## Screenshots and PDF

```bash
camoufox-cli screenshot              # Screenshot to stdout (base64)
camoufox-cli screenshot page.png     # Save to file
camoufox-cli screenshot --full p.png # Full page screenshot
camoufox-cli pdf output.pdf          # Save page as PDF
```

## Scroll

```bash
camoufox-cli scroll down             # Scroll down 500px (default)
camoufox-cli scroll up               # Scroll up 500px
camoufox-cli scroll down 1000        # Scroll down 1000px
```

## Wait

```bash
camoufox-cli wait @e1                # Wait for element to appear
camoufox-cli wait 2000               # Wait milliseconds
camoufox-cli wait --url "*/dashboard" # Wait for URL pattern
```

## Tabs

```bash
camoufox-cli tabs                    # List open tabs
camoufox-cli switch 2                # Switch to tab by index
camoufox-cli close-tab               # Close current tab
```

## Cookies

```bash
camoufox-cli cookies                 # Dump cookies as JSON
camoufox-cli cookies import file.json # Import cookies from file
camoufox-cli cookies export file.json # Export cookies to file
```

## Sessions

```bash
camoufox-cli sessions                # List active sessions
camoufox-cli --session <name> <cmd>  # Run command in named session
camoufox-cli close --all             # Close all sessions
```

## JavaScript

```bash
camoufox-cli eval "document.title"   # Simple expression
camoufox-cli eval "document.querySelectorAll('img').length"
```

For complex JavaScript with nested quotes, use shell escaping carefully or pipe via stdin.

## Setup

```bash
camoufox-cli install                 # Download Camoufox browser
camoufox-cli install --with-deps     # Download browser + system libs (Linux)
```

## Global Options

```bash
camoufox-cli --session <name> ...    # Isolated browser session
camoufox-cli --headed ...            # Show browser window (not headless)
camoufox-cli --json ...              # JSON output for parsing
camoufox-cli --timeout <seconds> ... # Daemon idle timeout (default: 1800)
camoufox-cli --persistent [path] ... # Use persistent browser profile (default: ~/.camoufox-cli/profiles/<session>)
camoufox-cli --proxy <url> ...      # Proxy server (e.g. http://host:port or http://user:pass@host:port)
camoufox-cli --no-geoip ...         # Disable automatic GeoIP spoofing (auto-enabled with --proxy)
camoufox-cli --locale <tag> ...     # Force browser locale (e.g. "en-US" or "en-US,zh-CN")
```
