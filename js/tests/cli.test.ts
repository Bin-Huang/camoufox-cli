import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildCommand, getSocketPath, parseArgs } from "../src/cli.js";

// buildCommand calls process.exit on error; mock it to throw instead
beforeEach(() => {
  vi.spyOn(process, "exit").mockImplementation((code) => {
    throw new Error(`process.exit(${code})`);
  });
  vi.spyOn(process.stderr, "write").mockImplementation(() => true);
});

describe("buildCommand", () => {
  // --- Navigation ---
  it("open", () => {
    const cmd = buildCommand("open", ["open", "https://example.com"]);
    expect(cmd.action).toBe("open");
    expect((cmd.params as any).url).toBe("https://example.com");
  });

  it("back", () => {
    const cmd = buildCommand("back", ["back"]);
    expect(cmd.action).toBe("back");
  });

  it("forward", () => {
    const cmd = buildCommand("forward", ["forward"]);
    expect(cmd.action).toBe("forward");
  });

  it("reload", () => {
    const cmd = buildCommand("reload", ["reload"]);
    expect(cmd.action).toBe("reload");
  });

  it("url", () => {
    const cmd = buildCommand("url", ["url"]);
    expect(cmd.action).toBe("url");
  });

  it("title", () => {
    const cmd = buildCommand("title", ["title"]);
    expect(cmd.action).toBe("title");
  });

  it("close", () => {
    const cmd = buildCommand("close", ["close"]);
    expect(cmd.action).toBe("close");
  });

  it("close --all", () => {
    const cmd = buildCommand("close", ["close", "--all"]);
    expect((cmd.params as any).all).toBe(true);
  });

  // --- Snapshot ---
  it("snapshot basic", () => {
    const cmd = buildCommand("snapshot", ["snapshot"]);
    expect(cmd.action).toBe("snapshot");
    expect((cmd.params as any).interactive).toBe(false);
  });

  it("snapshot interactive", () => {
    const cmd = buildCommand("snapshot", ["snapshot", "-i"]);
    expect((cmd.params as any).interactive).toBe(true);
  });

  it("snapshot scoped", () => {
    const cmd = buildCommand("snapshot", ["snapshot", "-s", "#main"]);
    expect((cmd.params as any).selector).toBe("#main");
  });

  // --- Interaction ---
  it("click", () => {
    const cmd = buildCommand("click", ["click", "@e1"]);
    expect(cmd.action).toBe("click");
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("fill", () => {
    const cmd = buildCommand("fill", ["fill", "@e1", "hello"]);
    expect((cmd.params as any).ref).toBe("@e1");
    expect((cmd.params as any).text).toBe("hello");
  });

  it("type", () => {
    const cmd = buildCommand("type", ["type", "@e1", "hello"]);
    expect((cmd.params as any).ref).toBe("@e1");
    expect((cmd.params as any).text).toBe("hello");
  });

  it("select", () => {
    const cmd = buildCommand("select", ["select", "@e1", "Option A"]);
    expect((cmd.params as any).ref).toBe("@e1");
    expect((cmd.params as any).value).toBe("Option A");
  });

  it("check", () => {
    const cmd = buildCommand("check", ["check", "@e1"]);
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("hover", () => {
    const cmd = buildCommand("hover", ["hover", "@e1"]);
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("press", () => {
    const cmd = buildCommand("press", ["press", "Enter"]);
    expect((cmd.params as any).key).toBe("Enter");
  });

  // --- Data extraction ---
  it("text", () => {
    const cmd = buildCommand("text", ["text", "@e1"]);
    expect((cmd.params as any).target).toBe("@e1");
  });

  it("eval", () => {
    const cmd = buildCommand("eval", ["eval", "document.title"]);
    expect((cmd.params as any).expression).toBe("document.title");
  });

  it("screenshot with path", () => {
    const cmd = buildCommand("screenshot", ["screenshot", "out.png"]);
    expect((cmd.params as any).path).toBe("out.png");
  });

  it("screenshot --full with path", () => {
    const cmd = buildCommand("screenshot", ["screenshot", "--full", "out.png"]);
    expect((cmd.params as any).full_page).toBe(true);
    expect((cmd.params as any).path).toBe("out.png");
  });

  it("screenshot no args", () => {
    const cmd = buildCommand("screenshot", ["screenshot"]);
    expect((cmd.params as any).path).toBeUndefined();
  });

  it("pdf", () => {
    const cmd = buildCommand("pdf", ["pdf", "output.pdf"]);
    expect(cmd.action).toBe("pdf");
    expect((cmd.params as any).path).toBe("output.pdf");
  });

  // --- Scroll & Wait ---
  it("scroll down default", () => {
    const cmd = buildCommand("scroll", ["scroll", "down"]);
    expect((cmd.params as any).direction).toBe("down");
    expect((cmd.params as any).amount).toBe(500);
  });

  it("scroll up custom amount", () => {
    const cmd = buildCommand("scroll", ["scroll", "up", "300"]);
    expect((cmd.params as any).direction).toBe("up");
    expect((cmd.params as any).amount).toBe(300);
  });

  it("wait ms", () => {
    const cmd = buildCommand("wait", ["wait", "2000"]);
    expect((cmd.params as any).ms).toBe(2000);
  });

  it("wait ref", () => {
    const cmd = buildCommand("wait", ["wait", "@e1"]);
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("wait selector", () => {
    const cmd = buildCommand("wait", ["wait", "#loading"]);
    expect((cmd.params as any).selector).toBe("#loading");
  });

  it("wait --url", () => {
    const cmd = buildCommand("wait", ["wait", "--url", "*/dashboard"]);
    expect((cmd.params as any).url).toBe("*/dashboard");
  });

  // --- Tabs ---
  it("tabs", () => {
    const cmd = buildCommand("tabs", ["tabs"]);
    expect(cmd.action).toBe("tabs");
  });

  it("switch", () => {
    const cmd = buildCommand("switch", ["switch", "2"]);
    expect((cmd.params as any).index).toBe(2);
  });

  it("close-tab", () => {
    const cmd = buildCommand("close-tab", ["close-tab"]);
    expect(cmd.action).toBe("close-tab");
  });

  // --- Session ---
  it("sessions", () => {
    const cmd = buildCommand("sessions", ["sessions"]);
    expect(cmd.action).toBe("sessions");
  });

  it("install", () => {
    const cmd = buildCommand("install", ["install"]);
    expect(cmd.action).toBe("install");
  });

  it("install --with-deps", () => {
    const cmd = buildCommand("install", ["install", "--with-deps"]);
    expect((cmd.params as any).with_deps).toBe(true);
  });

  // --- Cookies ---
  it("cookies list", () => {
    const cmd = buildCommand("cookies", ["cookies"]);
    expect((cmd.params as any).op).toBe("list");
  });

  it("cookies export", () => {
    const cmd = buildCommand("cookies", ["cookies", "export", "c.json"]);
    expect((cmd.params as any).op).toBe("export");
    expect((cmd.params as any).path).toBe("c.json");
  });

  it("cookies import", () => {
    const cmd = buildCommand("cookies", ["cookies", "import", "c.json"]);
    expect((cmd.params as any).op).toBe("import");
    expect((cmd.params as any).path).toBe("c.json");
  });

  // --- Error cases ---
  it("unknown command exits", () => {
    expect(() => buildCommand("nonexistent", ["nonexistent"])).toThrow("process.exit");
  });

  it("open missing url exits", () => {
    expect(() => buildCommand("open", ["open"])).toThrow("process.exit");
  });

  it("click missing ref exits", () => {
    expect(() => buildCommand("click", ["click"])).toThrow("process.exit");
  });

  it("fill missing text exits", () => {
    expect(() => buildCommand("fill", ["fill", "@e1"])).toThrow("process.exit");
  });

  it("pdf missing path exits", () => {
    expect(() => buildCommand("pdf", ["pdf"])).toThrow("process.exit");
  });

  it("switch missing index exits", () => {
    expect(() => buildCommand("switch", ["switch"])).toThrow("process.exit");
  });

  // --- ID field ---
  it("all commands have id=r1", () => {
    const cmd = buildCommand("back", ["back"]);
    expect(cmd.id).toBe("r1");
  });
});

describe("parseArgs", () => {
  it("defaults", () => {
    const { flags } = parseArgs(["open", "https://example.com"]);
    expect(flags.session).toBe("default");
    expect(flags.headed).toBe(false);
    expect(flags.timeout).toBe(1800);
    expect(flags.json).toBe(false);
    expect(flags.persistent).toBeNull();
    expect(flags.proxy).toBeNull();
  });

  it("--proxy flag", () => {
    const { flags } = parseArgs(["--proxy", "http://127.0.0.1:8080", "open", "https://example.com"]);
    expect(flags.proxy).toBe("http://127.0.0.1:8080");
  });

  it("--proxy with auth", () => {
    const { flags } = parseArgs(["--proxy", "http://user:pass@host:8080", "open", "https://example.com"]);
    expect(flags.proxy).toBe("http://user:pass@host:8080");
  });

  it("--proxy missing value exits", () => {
    expect(() => parseArgs(["--proxy"])).toThrow("process.exit");
  });
});

describe("getSocketPath", () => {
  it("default session", () => {
    expect(getSocketPath("default")).toBe("/tmp/camoufox-cli-default.sock");
  });

  it("custom session", () => {
    expect(getSocketPath("my-session")).toBe("/tmp/camoufox-cli-my-session.sock");
  });
});
