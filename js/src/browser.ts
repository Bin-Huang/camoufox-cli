/** Browser manager: launches and manages Camoufox instance. */

import { existsSync, mkdirSync } from "node:fs";
import * as path from "node:path";
import { Camoufox, launchOptions } from "camoufox-js";
import { camoufoxPath } from "camoufox-js/dist/pkgman.js";
import { firefox, type Browser, type BrowserContext, type Page } from "playwright-core";
import { ensureMmdb } from "./install.js";
import { loadOrCreate, toLaunchOptions } from "./identity.js";
import { parseProxySettings } from "./proxy.js";
import { RefRegistry } from "./refs.js";

const MAX_HISTORY = 200;

function ensureBrowserInstalled(): void {
  // Check in-process against the BUNDLED camoufox-js. The old
  // `execFileSync("npx", ["camoufox-js", "path"])` probe was broken three
  // ways: npx resolves camoufox-js from the caller's cwd, so under a global
  // install it downloaded an arbitrary other version from the registry; that
  // needs network at browser-launch time; and in a non-TTY daemon it could
  // hang forever. camoufoxPath(false) has no download side effect — it
  // throws when the browser dir is missing or its version is unsupported.
  try {
    const dir = camoufoxPath(false).toString();
    const launcher =
      process.platform === "darwin"
        ? path.join(dir, "Camoufox.app", "Contents", "MacOS", "camoufox")
        : process.platform === "win32"
          ? path.join(dir, "camoufox.exe")
          : path.join(dir, "camoufox-bin");
    if (!existsSync(launcher)) throw new Error("launcher missing");
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
  // In-flight ctx.newPage() shared by concurrent commands for this tab, so
  // they don't each create (and orphan) a page. Cleared once it settles.
  pagePromise?: Promise<Page>;
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
  private recovering: Promise<void> | null = null;
  // Serializes releaseTab calls; see releaseTab for why.
  private releasing: Promise<void> = Promise.resolve();
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
    } catch (e) {
      // A failure partway through doLaunch can leave this.browser set but the
      // context/page missing; without this rollback every later launch() would
      // short-circuit on `this.browser || this.context` and wedge the daemon.
      await this.close();
      throw e;
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

  /**
   * Recover after the shared browser/context has died: close what's left and
   * relaunch. Concurrent callers coalesce onto ONE close+relaunch — the daemon
   * handles connections concurrently, so without this two tabs recovering at
   * once would each close+relaunch and one would tear down the browser the
   * other just created. (Python needs no equivalent: its daemon is serial.)
   */
  async recoverDeadBrowser(headless: boolean, tab: string): Promise<void> {
    if (!this.recovering) {
      this.recovering = (async () => {
        await this.close();
        await this.launch(headless, tab);
      })().finally(() => { this.recovering = null; });
    }
    await this.recovering;
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
   * Get the tab's page.
   *
   * With `create` (navigation commands only) a missing/closed page is lazily
   * (re)created in the shared context — a new tab gets its own page with the
   * same fingerprint and cookies as every other tab. Without it, a command on
   * a tab that never opened a page throws instead of silently operating on a
   * blank about:blank (which would also leak a stray page per misrouted tab).
   */
  async getPage(tab: string = "default", create: boolean = false): Promise<Page> {
    const ctx = this.getContext();
    const st = this.tabState(tab);
    if (!st.page || st.page.isClosed()) {
      if (!create) throw new Error(`Tab '${tab}' has no open page. Send 'open <url>' first.`);
      // The daemon handles connections concurrently, so cache the in-flight
      // newPage() — otherwise two commands for the same fresh tab each create
      // a page and one is orphaned in the context forever.
      st.pagePromise ??= ctx.newPage().finally(() => { st.pagePromise = undefined; });
      st.page = await st.pagePromise;
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
    // The refs and history describe the previous page, not this one — reset
    // them so a stale @ref can't resolve against the newly-adopted page.
    st.refs = new RefRegistry();
    st.history = [];
    st.historyIndex = -1;
    await st.page.bringToFront();
    return st.page;
  }

  /**
   * Close the named tab; last one out shuts down the whole browser.
   *
   * This is the 'close' command. Every caller — solo or one of many
   * concurrent agents — runs the same thing without knowing about the
   * others: it closes only the caller's own page (never a neighbor's,
   * which would hijack another agent's tab), and when no live tab remains
   * the browser itself is closed. Idempotent: releasing a tab that has no
   * open page is a no-op, not an error.
   *
   * Releases are SERIALIZED through a promise chain. Without it, N
   * concurrent closes interleave at the awaits: every one deletes its own
   * map entry first, then every survivor scan sees an emptied map, so all
   * N conclude they are the last tab out — the browser gets torn down N
   * times and isRunning flips false for every in-flight close, which made
   * the server destroy sibling connections before their responses flushed
   * (their tabs were released, but the clients never got the receipt).
   */
  releaseTab(tab: string): Promise<void> {
    const run = this.releasing.then(() => this.doReleaseTab(tab));
    // Keep the chain usable even if a release fails.
    this.releasing = run.catch(() => {});
    return run;
  }

  private async doReleaseTab(tab: string): Promise<void> {
    const st = this.tabs.get(tab);
    this.tabs.delete(tab);
    if (st?.page && !st.page.isClosed()) {
      try { await st.page.close(); } catch {}
    }
    // Tabs (not context pages) are the refcount: pages nobody owns —
    // window.open popups, pages of misrouted tab names — must not keep
    // the browser alive after the last real tab leaves.
    for (const other of this.tabs.values()) {
      if (other.page && !other.page.isClosed()) return;
    }
    await this.close();
  }

  async goBack(tab: string = "default"): Promise<string | null> {
    const st = this.tabState(tab);
    if (st.historyIndex <= 0) return null;
    st.historyIndex--;
    const url = st.history[st.historyIndex];
    await (await this.getPage(tab, true)).goto(url, { waitUntil: "domcontentloaded" });
    return url;
  }

  async goForward(tab: string = "default"): Promise<string | null> {
    const st = this.tabState(tab);
    if (st.historyIndex >= st.history.length - 1) return null;
    st.historyIndex++;
    const url = st.history[st.historyIndex];
    await (await this.getPage(tab, true)).goto(url, { waitUntil: "domcontentloaded" });
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

  recoverDeadBrowser(headless: boolean = true): Promise<void> {
    return this.manager.recoverDeadBrowser(headless, this.tab);
  }

  getPage(create: boolean = false): Promise<Page> {
    return this.manager.getPage(this.tab, create);
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

  pushHistory(url: string): void {
    this.manager.tabState(this.tab).pushHistory(url);
  }

  goBack(): Promise<string | null> {
    return this.manager.goBack(this.tab);
  }

  goForward(): Promise<string | null> {
    return this.manager.goForward(this.tab);
  }

  /** Close this tab; the browser shuts down when the last tab leaves. */
  release(): Promise<void> {
    return this.manager.releaseTab(this.tab);
  }

  /** Force-close the whole browser regardless of other tabs (close --all). */
  shutdown(): Promise<void> {
    return this.manager.close();
  }
}
