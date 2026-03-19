import { beforeEach, describe, expect, it, vi } from "vitest";

const execFileSyncMock = vi.fn();
const camoufoxMock = vi.fn();
const launchOptionsMock = vi.fn();
const launchMock = vi.fn();
const launchPersistentContextMock = vi.fn();

vi.mock("node:child_process", () => ({
  execFileSync: execFileSyncMock,
}));

vi.mock("camoufox-js", () => ({
  Camoufox: camoufoxMock,
  launchOptions: launchOptionsMock,
}));

vi.mock("playwright-core", () => ({
  firefox: {
    launch: launchMock,
    launchPersistentContext: launchPersistentContextMock,
  },
}));

const BETTER_SQLITE_ROOT_ERROR =
  'Could not find module root given file: "/tmp/node_modules/better-sqlite3/lib/database.js". Do you have a `package.json` file?';

describe("BrowserManager launch fallback", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    execFileSyncMock.mockReturnValue(Buffer.from(""));
  });

  it("retries persistent launch with WebGL disabled when better-sqlite3 root lookup fails", async () => {
    const page = {};
    const context = {
      pages: vi.fn(() => []),
      newPage: vi.fn(async () => page),
    };

    launchOptionsMock
      .mockRejectedValueOnce(new Error(BETTER_SQLITE_ROOT_ERROR))
      .mockResolvedValueOnce({ headless: false, firefoxUserPrefs: { "webgl.disabled": true } });
    launchPersistentContextMock.mockResolvedValue(context);

    const stderrWrite = vi.spyOn(process.stderr, "write").mockReturnValue(true);
    const { BrowserManager } = await import("../src/browser.js");

    const manager = new BrowserManager("/tmp/profile");
    await manager.launch(false);

    expect(launchOptionsMock).toHaveBeenNthCalledWith(1, { headless: false });
    expect(launchOptionsMock).toHaveBeenNthCalledWith(2, { headless: false, block_webgl: true });
    expect(launchPersistentContextMock).toHaveBeenCalledWith(
      "/tmp/profile",
      { headless: false, firefoxUserPrefs: { "webgl.disabled": true } },
    );
    expect(stderrWrite).toHaveBeenCalledWith(
      "[camoufox-cli] better-sqlite3 failed while loading WebGL data; retrying with WebGL spoofing disabled\n",
    );
    expect(manager.getContext()).toBe(context);

    stderrWrite.mockRestore();
  });

  it("retries non-persistent launch with Playwright when Camoufox hits the same loader failure", async () => {
    const context = {};
    const page = {
      context: vi.fn(() => context),
    };
    const browser = {
      newPage: vi.fn(async () => page),
    };

    camoufoxMock.mockRejectedValueOnce(new Error(BETTER_SQLITE_ROOT_ERROR));
    launchOptionsMock.mockResolvedValueOnce({ headless: true, firefoxUserPrefs: { "webgl.disabled": true } });
    launchMock.mockResolvedValue(browser);

    const stderrWrite = vi.spyOn(process.stderr, "write").mockReturnValue(true);
    const { BrowserManager } = await import("../src/browser.js");

    const manager = new BrowserManager();
    await manager.launch(true);

    expect(camoufoxMock).toHaveBeenCalledWith({ headless: true });
    expect(launchOptionsMock).toHaveBeenCalledWith({ headless: true, block_webgl: true });
    expect(launchMock).toHaveBeenCalledWith({ headless: true, firefoxUserPrefs: { "webgl.disabled": true } });
    expect(manager.getPage()).toBe(page);
    expect(manager.getContext()).toBe(context);
    expect(stderrWrite).toHaveBeenCalledWith(
      "[camoufox-cli] better-sqlite3 failed while loading WebGL data; retrying with WebGL spoofing disabled\n",
    );

    stderrWrite.mockRestore();
  });
});