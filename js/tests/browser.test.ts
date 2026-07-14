import { describe, it, expect, vi } from "vitest";
import { BrowserManager } from "../src/browser.js";

describe("BrowserManager", () => {
  it("starts as not running", () => {
    const manager = new BrowserManager();
    expect(manager.isRunning).toBe(false);
  });

  it("recoverDeadBrowser coalesces concurrent callers into one relaunch", async () => {
    const manager = new BrowserManager();
    let closes = 0, launches = 0;
    vi.spyOn(manager, "close").mockImplementation(async () => {
      closes++; await new Promise((r) => setTimeout(r, 10));
    });
    vi.spyOn(manager, "launch").mockImplementation(async () => {
      launches++; await new Promise((r) => setTimeout(r, 10));
    });

    // Five tabs recovering from a dead browser at once must share ONE
    // close+relaunch, not stomp each other's freshly launched browser.
    await Promise.all([0, 1, 2, 3, 4].map(() => manager.recoverDeadBrowser(true, "t")));
    expect(closes).toBe(1);
    expect(launches).toBe(1);

    // A later, separate recovery runs fresh (the in-flight promise was cleared).
    await manager.recoverDeadBrowser(true, "t");
    expect(closes).toBe(2);
    expect(launches).toBe(2);
  });

  it("getPage rejects when not launched", async () => {
    const manager = new BrowserManager();
    await expect(manager.getPage()).rejects.toThrow("not launched");
  });

  it("getContext throws when not launched", () => {
    const manager = new BrowserManager();
    expect(() => manager.getContext()).toThrow("not launched");
  });

  it("close on non-running is safe", async () => {
    const manager = new BrowserManager();
    await manager.close(); // should not throw
    expect(manager.isRunning).toBe(false);
  });

  it("has empty refs on creation", () => {
    const manager = new BrowserManager();
    expect(manager.tabState("default").refs.size).toBe(0);
  });

  it("keeps per-tab refs independent", () => {
    const manager = new BrowserManager();
    expect(manager.tabState("a").refs).not.toBe(manager.tabState("b").refs);
    expect(manager.tabState("a").refs).toBe(manager.tabState("a").refs);
  });
});

describe("TabState history", () => {
  it("pushHistory tracks urls", () => {
    const st = new BrowserManager().tabState("default");
    st.pushHistory("https://a.com");
    st.pushHistory("https://b.com");
    st.pushHistory("https://c.com");
    expect(st.history).toEqual(["https://a.com", "https://b.com", "https://c.com"]);
    expect(st.historyIndex).toBe(2);
  });

  it("pushHistory truncates forward history", () => {
    const st = new BrowserManager().tabState("default");
    st.pushHistory("https://a.com");
    st.pushHistory("https://b.com");
    st.pushHistory("https://c.com");
    st.historyIndex = 0; // simulate having gone back to a.com
    st.pushHistory("https://d.com");
    expect(st.history).toEqual(["https://a.com", "https://d.com"]);
    expect(st.historyIndex).toBe(1);
  });

  it("history is independent per tab", () => {
    const manager = new BrowserManager();
    manager.tabState("a").pushHistory("https://a.com");
    expect(manager.tabState("b").history).toEqual([]);
  });
});

describe("BrowserManager persistent mode", () => {
  it("accepts persistent path in constructor", () => {
    const manager = new BrowserManager("/tmp/test-profile");
    expect(manager.isRunning).toBe(false);
  });

  it("defaults persistent to null", () => {
    const manager = new BrowserManager();
    expect(manager.isRunning).toBe(false);
  });
});
