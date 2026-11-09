/**
 * Usage guide that `camoufox-cli skill` prints.
 *
 * The canonical guide lives in the Python package (src/camoufox_cli/guide).
 * Every `npm pack` (and so `npm publish`) copies it to js/guide, so an agent always reads the guide for
 * the installed CLI version. The entry skill in skills/camoufox-cli only tells
 * agents to run `camoufox-cli skill`.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export const TOPICS = ["usage", "commands", "snapshot-refs"] as const;
export const SKILL_USAGE = "Usage: camoufox-cli skill [commands|snapshot-refs]";

export function unknownTopicMessage(topic: string): string {
  return `Unknown topic: ${topic}\n${SKILL_USAGE}`;
}
export const HELP_ARGS: readonly string[] = ["help", "--help", "-h"];
// After a command, only flags ask for help: `text help` targets a selector named "help".
export const HELP_FLAGS: readonly string[] = ["--help", "-h"];

// Commands that older guides taught. An agent with a stale skill still runs them.
export const REMOVED_COMMANDS: Record<string, string> = {
  "close-tab": "`close` now closes only your tab; use `--tab <name> close` for a named tab",
};

const here = path.dirname(fileURLToPath(import.meta.url));

/** js/guide in the npm package; src/camoufox_cli/guide in a repo checkout. */
export function guideDir(): string {
  const packaged = path.join(here, "..", "guide");
  if (fs.existsSync(packaged)) return packaged;
  return path.join(here, "..", "..", "src", "camoufox_cli", "guide");
}

/**
 * The guide for `topic`, between a version line and an end line.
 * Agents check for the end line to detect truncated command output.
 */
export function renderGuide(topic: string, version: string, dir: string = guideDir()): string {
  const file = path.join(dir, `${topic}.md`);
  if (!fs.existsSync(file)) {
    process.stderr.write(`Error: the usage guide is missing from this install (${file}). Reinstall camoufox-cli.\n`);
    process.exit(1);
  }
  const body = fs.readFileSync(file, "utf8");
  return (
    `[camoufox-cli:skill] ${topic} guide v${version}\n\n` +
    `${body.trim()}\n\n` +
    `[camoufox-cli:skill] end of ${topic} guide v${version}\n`
  );
}

/** Error text for an unknown command, with a hint for agents whose skill is stale. */
export function unknownCommandMessage(action: string, version: string): string {
  const lines = [`Unknown command: ${action}`];
  if (action.startsWith("-") && action.includes(" ")) {
    // e.g. T="--tab x"; camoufox-cli $T ...  (zsh does not split $T into words)
    lines.push(
      `\`${action}\` reached camoufox-cli as one argument. Pass the flag and its value ` +
        "as two arguments. zsh does not split an unquoted $VAR into words.",
    );
    return lines.join("\n");
  }
  // Own keys only: `in` would also match inherited names such as "toString".
  if (Object.hasOwn(REMOVED_COMMANDS, action)) {
    lines.push(`\`${action}\` was removed: ${REMOVED_COMMANDS[action]}.`);
  }
  lines.push(
    `If a skill or guide told you to run this, it may not match camoufox-cli v${version}. ` +
      "Run `camoufox-cli skill` to read the guide for this version.",
  );
  return lines.join("\n");
}
