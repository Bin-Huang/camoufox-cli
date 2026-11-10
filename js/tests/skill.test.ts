import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildCommand } from "../src/cli.js";
import { TOPICS, guideDir, renderGuide, unknownCommandMessage } from "../src/skill.js";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
// Claude Code keeps 30,000 characters of command output. Leave headroom so the
// end line, which agents use to detect truncation, is never cut off.
const MAX_GUIDE_CHARS = 25_000;

beforeEach(() => {
  vi.spyOn(process, "exit").mockImplementation((code) => {
    throw new Error(`process.exit(${code})`);
  });
  vi.spyOn(process.stderr, "write").mockImplementation(() => true);
  process.env.CAMOUFOX_CLI_CONFIG = path.join(os.tmpdir(), "camoufox-cli-absent-dir", "config.json");
});

describe("skill command", () => {
  it("defaults to the usage topic", () => {
    expect(buildCommand("skill", ["skill"])).toEqual({ id: "r1", action: "skill", params: { topic: "usage" } });
  });

  it.each(TOPICS)("accepts topic %s", (topic) => {
    expect(buildCommand("skill", ["skill", topic]).params).toEqual({ topic });
  });

  it("rejects an unknown topic", () => {
    expect(() => buildCommand("skill", ["skill", "nope"])).toThrow("process.exit");
    expect(process.stderr.write).toHaveBeenCalledWith(expect.stringMatching(/^Unknown topic: nope\nUsage: camoufox-cli skill/));
  });

  it("rejects an extra argument", () => {
    expect(() => buildCommand("skill", ["skill", "commands", "extra"])).toThrow("process.exit");
  });
});

describe("renderGuide", () => {
  it("reads the canonical guide in a repo checkout", () => {
    expect(guideDir()).toBe(path.join(repo, "src", "camoufox_cli", "guide"));
  });

  it.each(TOPICS)("wraps %s between version and end lines", (topic) => {
    const source = fs.readFileSync(path.join(repo, "src", "camoufox_cli", "guide", `${topic}.md`), "utf8");
    expect(renderGuide(topic, "1.2.3")).toBe(
      `[camoufox-cli:skill] ${topic} guide v1.2.3\n\n${source.trim()}\n\n[camoufox-cli:skill] end of ${topic} guide v1.2.3\n`,
    );
  });

  it.each(TOPICS)("keeps %s under the agent output limit", (topic) => {
    expect(renderGuide(topic, "0.0.0").length).toBeLessThan(MAX_GUIDE_CHARS);
  });
});

describe("help", () => {
  it.each([["--help"], ["-h"], ["help"], ["click", "--help"], ["snapshot", "-h"]])("prints usage for %s and exits 0", (...rest) => {
    const write = vi.spyOn(process.stdout, "write").mockImplementation(() => true);
    expect(() => buildCommand(rest[0], rest)).toThrow("process.exit(0)");
    expect(write).toHaveBeenCalledWith(expect.stringMatching(/^Usage: camoufox-cli \[flags\][\s\S]*skill \[topic\]/));
  });
});

describe("help as a value", () => {
  it.each([["fill", "@e1", "--help"], ["type", "@e1", "-h"], ["eval", "1", "--help"], ["text", "help"], ["eval", "help"]])("passes %s through", (...rest) => {
    expect(buildCommand(rest[0], rest).action).toBe(rest[0]);
  });
});

// Needs `npm run build`; skipped without a build, like the process tests in cli.test.ts.
const cliJs = path.join(repo, "js", "dist", "cli.js");
describe.skipIf(!fs.existsSync(cliJs))("skill process", () => {
  const run = (...args: string[]) =>
    spawnSync(process.execPath, [cliJs, ...args], { encoding: "utf-8", timeout: 15000, env: { ...process.env } });

  it("prints the guide to stdout", () => {
    const res = run("skill");
    expect(res.status).toBe(0);
    expect(res.stdout.startsWith("[camoufox-cli:skill] usage guide v")).toBe(true);
    expect(res.stdout.trimEnd().split("\n").at(-1)).toMatch(/^\[camoufox-cli:skill\] end of usage guide v/);
  });

  it("accepts flags before skill", () => {
    const res = run("--session", "unused-skill-test", "--tab", "x", "skill", "commands");
    expect(res.status).toBe(0);
    expect(res.stdout.startsWith("[camoufox-cli:skill] commands guide v")).toBe(true);
  });
});

describe("unknown command", () => {
  it("points to camoufox-cli skill", () => {
    const msg = unknownCommandMessage("frobnicate", "1.2.3");
    expect(msg.startsWith("Unknown command: frobnicate\n")).toBe(true);
    expect(msg).toContain("If a skill or guide told you to run this");
    expect(msg).toContain("camoufox-cli v1.2.3");
    expect(msg).toContain("Run `camoufox-cli skill`");
  });

  it("explains a flag and value passed as one argument", () => {
    const msg = unknownCommandMessage("--tab scan-1a2b", "1.2.3");
    expect(msg).toContain("reached camoufox-cli as one argument");
    expect(msg).not.toContain("camoufox-cli skill");
  });

  it.each(["toString", "constructor", "__proto__"])("does not treat %s as a removed command", (name) => {
    expect(unknownCommandMessage(name, "1.2.3")).not.toContain("was removed");
  });

  it("names the replacement for a removed command", () => {
    const msg = unknownCommandMessage("close-tab", "1.2.3");
    expect(msg).toContain("`close-tab` was removed");
    expect(msg).toContain("--tab <name> close");
  });

  it("is printed by buildCommand", () => {
    expect(() => buildCommand("close-tab", ["close-tab"])).toThrow("process.exit");
    expect(process.stderr.write).toHaveBeenCalledWith(expect.stringContaining("`close-tab` was removed"));
  });
});
