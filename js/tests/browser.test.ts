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

  it("concurrent releases: only the true last tab out closes the browser", async () => {
    const manager = new BrowserManager();
    let closes = 0;
    vi.spyOn(manager, "close").mockImplementation(async () => { closes++; });
    // Fake pages that take a moment to close, forcing the releases to
    // interleave at the await — the exact shape of the production race.
    const mkTab = () => ({
      page: { isClosed: () => false, close: () => new Promise((r) => setTimeout(r, 20)) },
    });
    (manager as any).tabs.set("a", mkTab());
    (manager as any).tabs.set("b", mkTab());
    (manager as any).tabs.set("c", mkTab());

    await Promise.all([
      manager.releaseTab("a"),
      manager.releaseTab("b"),
      manager.releaseTab("c"),
    ]);
    // Unserialized, every release sees an emptied map and all three "close
    // the browser"; serialized, only the genuine last one does.
    expect(closes).toBe(1);
    expect((manager as any).tabs.size).toBe(0);
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
