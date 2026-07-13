/** Browser manager: launches and manages Camoufox instance. */

import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { Camoufox, launchOptions } from "camoufox-js";
import { firefox, type Browser, type BrowserContext, type Page } from "playwright-core";
import { ensureMmdb } from "./install.js";
import { loadOrCreate, toLaunchOptions } from "./identity.js";
import { parseProxySettings } from "./proxy.js";
import { RefRegistry } from "./refs.js";

const MAX_HISTORY = 200;

function ensureBrowserInstalled(): void {
  try {
    execFileSync("npx", ["camoufox-js", "path"], { stdio: "pipe" });
  } catch {
    throw new Error(
      "Browser not found. Run `camoufox-cli install` to download it."
    );
  }
}

/**
 * Per-tab state: page pointer, element refs, and navigation history.
 *
 * Every named tab shares the single browser context (same fingerprint,
 * same cookies/login state) but keeps its own page and view state, so
 * concurrent clients don't clobber each other.
 */
export class TabState {
  page: Page | null = null;
  refs = new RefRegistry();
  // Camoufox spoofs history API for anti-fingerprinting,
  // so we track navigation history ourselves.
  history: string[] = [];
  historyIndex = -1;

  pushHistory(url: string): void {
    this.history = this.history.slice(0, this.historyIndex + 1);
    this.history.push(url);
    if (this.history.length > MAX_HISTORY) {
      this.history = this.history.slice(-MAX_HISTORY);
    }
    this.historyIndex = this.history.length - 1;
  }
}

export class BrowserManager {
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private tabs = new Map<string, TabState>();
  private launching: Promise<void> | null = null;
  private persistent: string | null;
  private proxy: string | null;
  private geoip: boolean;
  private locale: string | null;

  constructor(persistent: string | null = null, proxy: string | null = null, geoip: boolean = true, locale: string | null = null) {
    this.persistent = persistent;
    this.proxy = proxy;
    this.geoip = geoip;
    this.locale = locale;
  }

  async launch(headless: boolean = true, tab: string = "default"): Promise<void> {
    // Serialize concurrent launches (several tabs' first "open" arriving
    // together) so exactly one browser is created.
    while (this.launching) await this.launching;
    if (this.browser || this.context) return;
    this.launching = this.doLaunch(headless, tab);
    try {
      await this.launching;
    } finally {
      this.launching = null;
    }
  }

  private async doLaunch(headless: boolean, tab: string): Promise<void> {
    ensureBrowserInstalled();

    if (this.proxy && this.geoip) {
      // Geoip resolution lazily downloads the GeoIP db via the rate-limited
      // GitHub API; fetch it through the resilient path first.
      await ensureMmdb();
    }

    const launchOpts: Record<string, unknown> = { headless };
    let proxySettings: { server: string; username?: string; password?: string } | null = null;
    if (this.proxy) {
      const settings = parseProxySettings(this.proxy);
      proxySettings = settings.proxy;
      launchOpts.proxy = settings.proxy;
      if (this.geoip) {
        launchOpts.geoip = true;
      }
    }

    if (this.persistent) {
      // Persistent identity: freeze fingerprint/OS on first launch; reload
      // it on subsequent launches. CLI-passed locale / proxy-derived geo
      // overwrite the stored values so the file tracks current intent.
      mkdirSync(this.persistent, { recursive: true });
      const identity = await loadOrCreate(
        this.persistent,
        this.locale,
        this.proxy,
        this.geoip,
      );
      Object.assign(launchOpts, toLaunchOptions(identity));
      const opts = await launchOptions(launchOpts);
      this.context = await firefox.launchPersistentContext(this.persistent, opts);
      const pages = this.context.pages();
      this.tabState(tab).page = pages[0] || await this.context.newPage();
    } else {
      if (this.locale) {
        // Non-persistent path: locale is a one-shot override, no identity file.
        const locales = this.locale.split(",").map((s) => s.trim()).filter(Boolean);
        if (locales.length > 0) {
          launchOpts.locale = locales.length > 1 ? locales : locales[0];
        }
      }
      this.browser = await Camoufox(launchOpts) as Browser;
      // Create an explicit context so more tabs can be added later — the
      // implicit context made by browser.newPage() refuses context.newPage().
      this.context = await this.browser.newContext();
      this.tabState(tab).page = await this.context.newPage();
    }

    // Workaround: Playwright's Firefox (Juggler) fails proxy auth on HTTPS
    // CONNECT tunnels, raising NS_ERROR_PROXY_AUTHENTICATION_FAILED.
    // Inject Basic auth as an extra HTTP header like WebKit/Chromium do.
    if (proxySettings?.username) {
      const creds = `${proxySettings.username}:${proxySettings.password ?? ""}`;
      const token = Buffer.from(creds, "utf8").toString("base64");
      await this.context.setExtraHTTPHeaders({
        "Proxy-Authorization": `Basic ${token}`,
      });
    }
  }

  /** Get (lazily creating) the state record for a named tab. */
  tabState(tab: string): TabState {
    let st = this.tabs.get(tab);
    if (!st) {
      st = new TabState();
      this.tabs.set(tab, st);
    }
    return st;
  }

  /**
   * Get the tab's page, lazily creating one in the shared context.
   *
   * A new tab gets its own page (same fingerprint and cookies as every
   * other tab); a tab whose page was closed gets a fresh one.
   */
  async getPage(tab: string = "default"): Promise<Page> {
    const ctx = this.getContext();
    const st = this.tabState(tab);
    if (!st.page || st.page.isClosed()) {
      st.page = await ctx.newPage();
    }
    return st.page;
  }

  getContext(): BrowserContext {
    if (!this.context) throw new Error("Browser not launched. Send 'open' command first.");
    return this.context;
  }

  async getTabsAsync(tab: string = "default"): Promise<{ index: number; url: string; title: string; active: boolean; tab: string | null }[]> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    const current = this.tabs.get(tab);
    const owners = new Map<Page, string>();
    for (const [name, st] of this.tabs) {
      if (st.page && !owners.has(st.page)) owners.set(st.page, name);
    }
    const tabs = [];
    for (let i = 0; i < pages.length; i++) {
      tabs.push({
        index: i,
        url: pages[i].url(),
        title: await pages[i].title(),
        active: current !== undefined && pages[i] === current.page,
        tab: owners.get(pages[i]) ?? null,
      });
    }
    return tabs;
  }

  async switchToTab(tab: string, index: number): Promise<Page> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    if (index < 0 || index >= pages.length) {
      throw new RangeError(`Tab index ${index} out of range (0-${pages.length - 1})`);
    }
    const st = this.tabState(tab);
    st.page = pages[index];
    await st.page.bringToFront();
    return st.page;
  }

  async closeCurrentTab(tab: string = "default"): Promise<void> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    if (pages.length <= 1) {
      throw new Error("Cannot close the last tab. Use 'close' to shut down the browser.");
    }
    const st = this.tabs.get(tab);
    if (!st?.page || st.page.isClosed()) {
      throw new Error(`Tab '${tab}' has no open page.`);
    }
    const current = st.page;
    const idx = pages.indexOf(current);
    const newIdx = idx > 0 ? idx - 1 : 1;
    st.page = pages[newIdx];
    await st.page.bringToFront();
    await current.close();
  }

  async goBack(tab: string = "default"): Promise<string | null> {
    const st = this.tabState(tab);
    if (st.historyIndex <= 0) return null;
    st.historyIndex--;
    const url = st.history[st.historyIndex];
    await (await this.getPage(tab)).goto(url, { waitUntil: "domcontentloaded" });
    return url;
  }

  async goForward(tab: string = "default"): Promise<string | null> {
    const st = this.tabState(tab);
    if (st.historyIndex >= st.history.length - 1) return null;
    st.historyIndex++;
    const url = st.history[st.historyIndex];
    await (await this.getPage(tab)).goto(url, { waitUntil: "domcontentloaded" });
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
    this.tabs.clear();
  }

  get isRunning(): boolean {
    return this.browser !== null || this.context !== null;
  }
}

/**
 * BrowserManager scoped to one named tab.
 *
 * Command handlers work against this view, so each client's commands
 * route to its own page/refs/history while sharing the browser context
 * (fingerprint + cookies) with every other tab.
 */
export class TabView {
  constructor(private manager: BrowserManager, readonly tab: string) {}

  get refs(): RefRegistry {
    return this.manager.tabState(this.tab).refs;
  }

  get isRunning(): boolean {
    return this.manager.isRunning;
  }

  launch(headless: boolean = true): Promise<void> {
    return this.manager.launch(headless, this.tab);
  }

  getPage(): Promise<Page> {
    return this.manager.getPage(this.tab);
  }

  getContext(): BrowserContext {
    return this.manager.getContext();
  }

  getTabsAsync(): Promise<{ index: number; url: string; title: string; active: boolean; tab: string | null }[]> {
    return this.manager.getTabsAsync(this.tab);
  }

  switchToTab(index: number): Promise<Page> {
    return this.manager.switchToTab(this.tab, index);
  }

  closeCurrentTab(): Promise<void> {
    return this.manager.closeCurrentTab(this.tab);
  }

  pushHistory(url: string): void {
    this.manager.tabState(this.tab).pushHistory(url);
  }

  goBack(): Promise<string | null> {
    return this.manager.goBack(this.tab);
  }

  goForward(): Promise<string | null> {
    return this.manager.goForward(this.tab);
  }

  close(): Promise<void> {
    return this.manager.close();
  }
}
