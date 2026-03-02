# camoufox-cli

> Under active development. Not ready for use yet.

The missing [agent-browser](https://github.com/vercel-labs/agent-browser)-style CLI for [Camoufox](https://github.com/daijro/camoufox).

Anti-detect browser automation for AI agents — through simple shell commands.

## Quick Look

```bash
cfox open https://example.com       # Launch browser & navigate
cfox snapshot -i                     # Get interactive accessibility tree
# - link "More information..." [ref=e1]
cfox click @e1                       # Click by element reference
cfox close                           # Done
```
