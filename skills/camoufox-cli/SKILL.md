---
name: camoufox-cli
description: Anti-detect browser automation CLI & Skills for AI agents. Use when the user needs to interact with websites with bot detection, CAPTCHAs, or anti-bot blocks, including navigating pages, filling forms, clicking buttons, taking screenshots, extracting data, testing web apps, or automating any browser task that requires bypassing fingerprint checks.
---

# camoufox-cli

Once per conversation, before your first camoufox-cli command, run this command by itself, with no pipe or redirection:

```bash
camoufox-cli skill
```

It prints the usage guide for the camoufox-cli version on this machine. Use that guide as your reference for camoufox-cli commands, because it always matches the installed CLI. Do not use commands that you remember from other sources. Run it again after camoufox-cli is upgraded.

The guide starts with `[camoufox-cli:skill] usage guide v<version>` and ends with `[camoufox-cli:skill] end of usage guide v<version>`. If the end line is missing, or the output says that lines were omitted or truncated, you did not get the full guide. In that case, save the guide to a file and read the file in parts:

```bash
camoufox-cli skill > "${TMPDIR:-/tmp}/camoufox-cli-guide.md"
```

## If `camoufox-cli skill` fails

**`command not found`**: camoufox-cli is not installed. Ask the user before you install it. Install it with npm (Node.js 20.10+) or pipx, not both, then download the browser. camoufox-cli supports macOS and Linux. On Windows, run it inside WSL.

```bash
npm install -g camoufox-cli       # or: pipx install camoufox-cli
camoufox-cli install              # on Linux: camoufox-cli install --with-deps
```

**`Unknown command: skill`**: the installed camoufox-cli is older than this skill. Ask the user before you upgrade it. Upgrade it with the tool that installed it (`npm ls -g camoufox-cli` shows an npm install):

```bash
npm install -g camoufox-cli@latest   # or: pipx upgrade camoufox-cli
```

If the user does not want to upgrade, use only the commands in the usage text that the old version prints with the error.

After the fix, run `camoufox-cli skill` and continue the user's task.
