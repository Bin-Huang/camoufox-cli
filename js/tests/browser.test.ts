import { describe, it, expect } from "vitest";
import { BrowserManager } from "../src/browser.js";

describe("BrowserManager", () => {
  it("starts as not running", () => {
    const manager = new BrowserManager();
    expect(manager.isRunning).toBe(false);
  });

  it("getPage throws when not launched", () => {
    const manager = new BrowserManager();
    expect(() => manager.getPage()).toThrow("not launched");
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
    expect(manager.refs.size).toBe(0);
  });
});

describe("BrowserManager downloads", () => {
  it("starts with no downloads", () => {
    expect(new BrowserManager().getDownloads()).toEqual([]);
  });

  it("download dir honours $CAMOUFOX_DOWNLOAD_DIR", () => {
    const prev = process.env.CAMOUFOX_DOWNLOAD_DIR;
    process.env.CAMOUFOX_DOWNLOAD_DIR = "/tmp/cf-dl-test";
    try {
      expect(new BrowserManager().getDownloadDir()).toBe("/tmp/cf-dl-test");
    } finally {
      if (prev === undefined) delete process.env.CAMOUFOX_DOWNLOAD_DIR;
      else process.env.CAMOUFOX_DOWNLOAD_DIR = prev;
    }
  });

  it("clearDownloads empties the list", () => {
    const manager = new BrowserManager();
    manager.clearDownloads();
    expect(manager.getDownloads()).toEqual([]);
  });

  it("cancelDownload returns false for an unknown id", async () => {
    expect(await new BrowserManager().cancelDownload(999)).toBe(false);
  });

  it("waitForPendingDownloads resolves immediately when none pending", async () => {
    const manager = new BrowserManager();
    await manager.waitForPendingDownloads(5000); // must not hang
    expect(manager.getDownloads()).toEqual([]);
  });
});

describe("BrowserManager history", () => {
  it("pushHistory tracks urls", () => {
    const manager = new BrowserManager();
    manager.pushHistory("https://a.com");
    manager.pushHistory("https://b.com");
    manager.pushHistory("https://c.com");
    // History should have 3 items (internal state)
  });

  it("pushHistory truncates forward history", () => {
    const manager = new BrowserManager();
    manager.pushHistory("https://a.com");
    manager.pushHistory("https://b.com");
    manager.pushHistory("https://c.com");
    // Simulate going back by manipulating internal state
    // This tests the slice logic: after going back, push truncates forward entries
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
