# Snapshot and Refs

Compact element references for AI agents to interact with page elements efficiently.

**Related**: [commands.md](commands.md) for full command reference, [SKILL.md](../SKILL.md) for quick start.

## Contents

- [How Refs Work](#how-refs-work)
- [Snapshot Command](#the-snapshot-command)
- [Using Refs](#using-refs)
- [Ref Lifecycle](#ref-lifecycle)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## How Refs Work

Traditional approach:
```
Full DOM/HTML -> AI parses -> CSS selector -> Action (~3000-5000 tokens)
```

camoufox-cli approach:
```
Compact aria snapshot -> @refs assigned -> Direct interaction (~200-400 tokens)
```

Refs are sequential numbers (`@e1`, `@e2`, ...) assigned to elements during each snapshot based on DOM traversal order. The same element may get different refs across snapshots if the page content changes.

## The Snapshot Command

```bash
# Basic snapshot (shows full page structure)
camoufox-cli snapshot

# Interactive snapshot (-i flag) - RECOMMENDED
camoufox-cli snapshot -i

# Scoped to a specific container
camoufox-cli snapshot -s "#main-content"
camoufox-cli snapshot -i -s "form.login"
```

### Snapshot Output Format

```
- heading "Example Domain" [ref=e1]
- navigation
  - link "Home" [ref=e2]
  - link "Products" [ref=e3]
  - link "About" [ref=e4]
- button "Sign In" [ref=e5]
- main
  - heading "Welcome" [ref=e6]
  - textbox "Email" [ref=e7]
  - textbox "Password" [ref=e8]
  - button "Log In" [ref=e9]
- contentinfo
  - link "Privacy Policy" [ref=e10]
```

With `-i` (interactive only), non-interactive elements are filtered out:

```
- link "Home" [ref=e1]
- link "Products" [ref=e2]
- link "About" [ref=e3]
- button "Sign In" [ref=e4]
- textbox "Email" [ref=e5]
- textbox "Password" [ref=e6]
- button "Log In" [ref=e7]
- link "Privacy Policy" [ref=e8]
```

## Using Refs

Once you have refs, interact directly:

```bash
# Click the "Sign In" button
camoufox-cli click @e4

# Fill email input
camoufox-cli fill @e5 "user@example.com"

# Fill password
camoufox-cli fill @e6 "password123"

# Submit the form
camoufox-cli click @e7
```

## Ref Lifecycle

**IMPORTANT**: Refs are invalidated when the page changes!

Refs are assigned by sequential numbering during each snapshot. They are tied to that specific page state. After any change to the page, old refs may point to wrong elements or not exist at all.

```bash
# Get initial snapshot
camoufox-cli snapshot -i
# - button "Next" [ref=e1]

# Click triggers page change
camoufox-cli click @e1

# MUST re-snapshot to get new refs!
camoufox-cli snapshot -i
# - heading "Page 2" [ref=e1]  <- Different element now!
```

### What Invalidates Refs

- **Navigation**: clicking links, form submissions, redirects
- **Dynamic content**: dropdowns opening, modals appearing, AJAX updates
- **Scrolling**: if it triggers lazy loading of new content
- **JavaScript**: any DOM mutation that changes element order

### What Happens with Stale Refs

When you use a ref without re-snapshotting after a page change:
- The ref may point to a **different element** (wrong click target)
- The ref may **not exist** (error)
- The action may **silently succeed on the wrong element**

This is the most common source of automation errors. When in doubt, re-snapshot.

## Best Practices

### 1. Always Snapshot Before Interacting

```bash
# CORRECT
camoufox-cli open https://example.com
camoufox-cli snapshot -i          # Get refs first
camoufox-cli click @e1            # Use ref

# WRONG
camoufox-cli open https://example.com
camoufox-cli click @e1            # Ref doesn't exist yet!
```

### 2. Re-Snapshot After Navigation

```bash
camoufox-cli click @e5            # Navigates to new page
camoufox-cli snapshot -i          # Get new refs
camoufox-cli click @e1            # Use new refs
```

### 3. Re-Snapshot After Dynamic Changes

```bash
camoufox-cli click @e1            # Opens dropdown
camoufox-cli snapshot -i          # See dropdown items
camoufox-cli click @e7            # Select item
```

### 4. Scope Snapshots on Complex Pages

For pages with many elements, scope the snapshot to reduce noise:

```bash
camoufox-cli snapshot -i -s "#login-form"
camoufox-cli snapshot -i -s ".product-list"
```

### 5. Wait Before Snapshot on Slow Pages

```bash
camoufox-cli open https://slow-site.com
camoufox-cli wait 3000            # Wait for content to load
camoufox-cli snapshot -i          # Now snapshot
```

## Troubleshooting

### "Ref @eN not found"

```bash
# Ref was invalidated - re-snapshot
camoufox-cli snapshot -i
```

Common causes:
- Page navigated since last snapshot
- Dynamic content changed the DOM
- Never took a snapshot after opening the page

### Element Not Visible in Snapshot

```bash
# Scroll down to reveal element
camoufox-cli scroll down 1000
camoufox-cli snapshot -i

# Or wait for dynamic content
camoufox-cli wait 2000
camoufox-cli snapshot -i
```

### Too Many Elements

```bash
# Scope to specific container
camoufox-cli snapshot -i -s "#main"

# Or use text extraction for content-only
camoufox-cli text body
```

### Duplicate Elements (Same Role + Name)

When multiple elements have the same role and name (e.g., two "Submit" buttons), each gets a unique ref. The snapshot shows `[nth=N]` for disambiguation:

```
- button "Submit" [ref=e3]
- button "Submit" [ref=e7] [nth=1]
```

Both refs work independently. Use the one that corresponds to the element you need.
