/** Browser manager: launches and manages Camoufox instance. */

import { execFileSync } from "node:child_process";
import { Camoufox, launchOptions } from "camoufox-js";
import { firefox, type Browser, type BrowserContext, type Page } from "playwright-core";
import { RefRegistry } from "./refs.js";

function ensureBrowserInstalled(): void {
  try {
    execFileSync("npx", ["camoufox-js", "path"], { stdio: "pipe" });
  } catch {
    throw new Error(
      "Browser not found. Run `camoufox-cli install` to download it."
    );
  }
}

function isBetterSqliteBindingsRootError(error: unknown): boolean {
  const message = error instanceof Error
    ? `${error.message}\n${error.stack ?? ""}`
    : String(error);

  return message.includes("Could not find module root given file:")
    && message.includes("better-sqlite3");
}

function writeFallbackWarning(): void {
  process.stderr.write(
    "[camoufox-cli] better-sqlite3 failed while loading WebGL data; retrying with WebGL spoofing disabled\n",
  );
}

export class BrowserManager {
  refs = new RefRegistry();
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private page: Page | null = null;
  private persistent: string | null;
  private history: string[] = [];
  private historyIndex = -1;

  constructor(persistent: string | null = null) {
    this.persistent = persistent;
  }

  async launch(headless: boolean = true): Promise<void> {
    if (this.browser || this.context) return;

    ensureBrowserInstalled();

    if (this.persistent) {
      this.context = await this.launchPersistentContext(headless);
      const pages = this.context.pages();
      this.page = pages[0] || await this.context.newPage();
    } else {
      this.browser = await this.launchBrowser(headless);
      this.page = await this.browser.newPage();
      this.context = this.page.context();
    }
  }

  private async launchBrowser(headless: boolean): Promise<Browser> {
    try {
      return await Camoufox({ headless }) as Browser;
    } catch (error) {
      if (!isBetterSqliteBindingsRootError(error)) {
        throw error;
      }

      writeFallbackWarning();
      const opts = await launchOptions({ headless, block_webgl: true });
      return await firefox.launch(opts);
    }
  }

  private async launchPersistentContext(headless: boolean): Promise<BrowserContext> {
    try {
      const opts = await launchOptions({ headless });
      return await firefox.launchPersistentContext(this.persistent!, opts);
    } catch (error) {
      if (!isBetterSqliteBindingsRootError(error)) {
        throw error;
      }

      writeFallbackWarning();
      const opts = await launchOptions({ headless, block_webgl: true });
      return await firefox.launchPersistentContext(this.persistent!, opts);
    }
  }

  getPage(): Page {
    if (!this.page) throw new Error("Browser not launched. Send 'open' command first.");
    return this.page;
  }

  getContext(): BrowserContext {
    if (!this.context) throw new Error("Browser not launched. Send 'open' command first.");
    return this.context;
  }

  async getTabsAsync(): Promise<{ index: number; url: string; title: string; active: boolean }[]> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    const tabs = [];
    for (let i = 0; i < pages.length; i++) {
      tabs.push({
        index: i,
        url: pages[i].url(),
        title: await pages[i].title(),
        active: pages[i] === this.page,
      });
    }
    return tabs;
  }

  async switchToTab(index: number): Promise<Page> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    if (index < 0 || index >= pages.length) {
      throw new RangeError(`Tab index ${index} out of range (0-${pages.length - 1})`);
    }
    this.page = pages[index];
    await this.page.bringToFront();
    return this.page;
  }

  async closeCurrentTab(): Promise<void> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    if (pages.length <= 1) {
      throw new Error("Cannot close the last tab. Use 'close' to shut down the browser.");
    }
    const current = this.page!;
    const idx = pages.indexOf(current);
    const newIdx = idx > 0 ? idx - 1 : 1;
    this.page = pages[newIdx];
    await this.page.bringToFront();
    await current.close();
  }

  pushHistory(url: string): void {
    this.history = this.history.slice(0, this.historyIndex + 1);
    this.history.push(url);
    this.historyIndex = this.history.length - 1;
  }

  async goBack(): Promise<string | null> {
    if (this.historyIndex <= 0) return null;
    this.historyIndex--;
    const url = this.history[this.historyIndex];
    await this.getPage().goto(url, { waitUntil: "domcontentloaded" });
    return url;
  }

  async goForward(): Promise<string | null> {
    if (this.historyIndex >= this.history.length - 1) return null;
    this.historyIndex++;
    const url = this.history[this.historyIndex];
    await this.getPage().goto(url, { waitUntil: "domcontentloaded" });
    return url;
  }

  async close(): Promise<void> {
    if (this.browser) {
      try { await this.browser.close(); } catch {}
      this.browser = null;
    }
    if (this.context && !this.browser) {
      // persistent context: close context directly
      try { await this.context.close(); } catch {}
    }
    this.context = null;
    this.page = null;
    this.history = [];
    this.historyIndex = -1;
  }

  get isRunning(): boolean {
    return this.browser !== null || this.context !== null;
  }
}
