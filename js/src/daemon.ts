#!/usr/bin/env node
/** Entry point: daemon process (spawned by CLI). */

import { DaemonServer } from "./server.js";

const args = process.argv.slice(2);

function getArg(name: string, defaultValue: string): string {
  const idx = args.indexOf(name);
  return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : defaultValue;
}

const session = getArg("--session", "default");
const headless = !args.includes("--headed");
// Number, not parseInt: the CLI passes String(timeout), which is "1e+21" for a
// huge value, and parseInt("1e+21") is 1.
const timeout = Number(getArg("--timeout", "1800"));
const persistent = args.includes("--persistent") ? getArg("--persistent", "") || null : null;
const proxy = args.includes("--proxy") ? getArg("--proxy", "") || null : null;
const geoip = !args.includes("--no-geoip");
const locale = args.includes("--locale") ? getArg("--locale", "") || null : null;

const server = new DaemonServer({ session, headless, timeout, persistent, proxy, geoip, locale });

process.stderr.write(`[camoufox-cli] Starting daemon session=${session} headless=${headless}\n`);
server.start().catch((err) => {
  process.stderr.write(`[camoufox-cli] Fatal: ${err}\n`);
  process.exit(1);
});
