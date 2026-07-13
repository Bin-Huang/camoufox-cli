import { describe, it, expect } from "vitest";
import { BrowserManager } from "../src/browser.js";

describe("BrowserManager", () => {
  it("starts as not running", () => {
    const manager = new BrowserManager();
    expect(manager.isRunning).toBe(false);
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
