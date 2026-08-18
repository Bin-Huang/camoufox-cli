/**
 * End-to-end tests exercising daemon server + socket protocol + real browser.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import * as net from "node:net";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { DaemonServer } from "../src/server.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(__dirname, "../../tests/fixture.html");
const FIXTURE_URL = `file://${FIXTURE_PATH}`;

const TEST_SESSION = `e2e-${process.pid}-${Date.now()}`;
const SOCK_PATH = `/tmp/camoufox-cli-${TEST_SESSION}.sock`;

function sendCommand(sockPath: string, cmd: Record<string, unknown>): Promise<Record<string, any>> {
  return new Promise((resolve, reject) => {
    const client = net.createConnection(sockPath, () => {
      client.end(JSON.stringify(cmd) + "\n");
    });
    let data = "";
    client.on("data", chunk => { data += chunk.toString(); });
    client.on("end", () => {
      try {
        resolve(JSON.parse(data.trim()));
      } catch (e) {
        reject(new Error(`Failed to parse response: ${data}`));
      }
    });
    client.on("error", reject);
  });
}

function cmd(sockPath: string, action: string, params: Record<string, unknown> = {}, id = "r1", tab?: string) {
  const command: Record<string, unknown> = { id, action, params };
  if (tab !== undefined) command.tab = tab;
  return sendCommand(sockPath, command);
}

async function waitForSocket(sockPath: string, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(sockPath)) return;
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error(`Socket ${sockPath} not found after ${timeoutMs}ms`);
}

function findRef(snapshot: string, role: string): string {
  for (const line of snapshot.split("\n")) {
    if (line.includes(`- ${role}`) && line.includes("[ref=")) {
      const start = line.indexOf("[ref=") + 5;
      const end = line.indexOf("]", start);
      return "@" + line.slice(start, end);
    }
  }
  throw new Error(`No ref found for role '${role}' in snapshot`);
}

describe("e2e", { timeout: 120_000 }, () => {
  let serverPromise: Promise<void>;

  beforeAll(async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      headless: true,
      timeout: 300,
    });
    serverPromise = server.start();
    await waitForSocket(SOCK_PATH);

    // Open fixture page
    const resp = await cmd(SOCK_PATH, "open", { url: FIXTURE_URL });
    expect(resp.success).toBe(true);
  });

  afterAll(async () => {
    // Tests leave named tabs open, so a plain close would only release the
    // default tab and keep the daemon alive; force it.
    try {
      await cmd(SOCK_PATH, "close", { force: true });
    } catch {}
    await serverPromise;
  });

  it("open returns url and title", async () => {
    const urlResp = await cmd(SOCK_PATH, "url");
    expect(urlResp.success).toBe(true);
    expect(urlResp.data.url).toContain("fixture.html");

    const titleResp = await cmd(SOCK_PATH, "title");
    expect(titleResp.success).toBe(true);
    expect(titleResp.data.title).toBe("Test Fixture");
  });

  it("snapshot has refs", async () => {
    const resp = await cmd(SOCK_PATH, "snapshot");
    expect(resp.success).toBe(true);
    expect(resp.data.snapshot).toContain("[ref=");
  });

  it("fill textbox", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "textbox");

    const fillResp = await cmd(SOCK_PATH, "fill", { ref, text: "E2E-Alice" });
    expect(fillResp.success).toBe(true);

    const evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('name').value" });
    expect(evalResp.data.result).toBe("E2E-Alice");
  });

  it("click button", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "button");

    const clickResp = await cmd(SOCK_PATH, "click", { ref });
    expect(clickResp.success).toBe(true);

    const evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('output').textContent" });
    expect(evalResp.data.result).toBe("clicked");
  });

  it("select dropdown", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "combobox");

    const selResp = await cmd(SOCK_PATH, "select", { ref, value: "Green" });
    expect(selResp.success).toBe(true);

    const evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('color').value" });
    expect(evalResp.data.result).toBe("green");
  });

  it("check and uncheck", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "checkbox");

    // Check
    let resp = await cmd(SOCK_PATH, "check", { ref });
    expect(resp.success).toBe(true);
    let evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('agree').checked" });
    expect(evalResp.data.result).toBe(true);

    // Uncheck
    resp = await cmd(SOCK_PATH, "check", { ref });
    expect(resp.success).toBe(true);
    evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('agree').checked" });
    expect(evalResp.data.result).toBe(false);
  });

  it("scroll", async () => {
    const resp = await cmd(SOCK_PATH, "scroll", { direction: "down", amount: 100 });
    expect(resp.success).toBe(true);
  });

  it("wait ms", async () => {
    const resp = await cmd(SOCK_PATH, "wait", { ms: 50 });
    expect(resp.success).toBe(true);
  });

  it("press key", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "textbox");
    await cmd(SOCK_PATH, "click", { ref });

    const resp = await cmd(SOCK_PATH, "press", { key: "Tab" });
    expect(resp.success).toBe(true);
  });

  it("back and forward", async () => {
    // Navigate to second page (use data: URI since about:blank may fail)
    const openResp = await cmd(SOCK_PATH, "open", { url: "data:text/html,<h1>Page2</h1>" });
    expect(openResp.success).toBe(true);

    // Go back to fixture
    const backResp = await cmd(SOCK_PATH, "back");
    expect(backResp.success).toBe(true);
    expect(backResp.data.url).toContain("fixture.html");

    // Go forward
    const fwdResp = await cmd(SOCK_PATH, "forward");
    expect(fwdResp.success).toBe(true);

    // Return to fixture for remaining tests
    await cmd(SOCK_PATH, "open", { url: FIXTURE_URL });
  });

  it("tabs", async () => {
    const resp = await cmd(SOCK_PATH, "tabs");
    expect(resp.success).toBe(true);
    expect(resp.data.tabs.length).toBeGreaterThanOrEqual(1);
    expect(resp.data.tabs.some((t: any) => t.active)).toBe(true);
  });

  it("cookies", async () => {
    const resp = await cmd(SOCK_PATH, "cookies", { op: "list" });
    expect(resp.success).toBe(true);
    expect(resp.data).toHaveProperty("cookies");
  });

  it("named tab gets its own page in the shared context", async () => {
    await cmd(SOCK_PATH, "open", { url: FIXTURE_URL }); // default tab on fixture
    const openResp = await cmd(SOCK_PATH, "open", { url: "data:text/html,<title>TabA</title><h1>A</h1>" }, "r1", "a");
    expect(openResp.success).toBe(true);

    // default tab's page is untouched
    const defaultUrl = await cmd(SOCK_PATH, "url");
    expect(defaultUrl.data.url).toContain("fixture.html");
    const tabAUrl = await cmd(SOCK_PATH, "url", {}, "r1", "a");
    expect(tabAUrl.data.url).toMatch(/^data:/);

    // both pages live in the same shared context (same fingerprint/cookies)
    const tabsResp = await cmd(SOCK_PATH, "tabs");
    const owners = tabsResp.data.tabs.map((t: any) => t.tab);
    expect(owners).toContain("default");
    expect(owners).toContain("a");
  });

  it("refs are per tab", async () => {
    await cmd(SOCK_PATH, "open", { url: FIXTURE_URL });
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "textbox");

    // Snapshotting another tab must not clobber the default tab's refs
    await cmd(SOCK_PATH, "open", { url: "data:text/html,<button>Only</button>" }, "r1", "a");
    await cmd(SOCK_PATH, "snapshot", {}, "r1", "a");

    const fillResp = await cmd(SOCK_PATH, "fill", { ref, text: "still-works" });
    expect(fillResp.success).toBe(true);
  });

  it("history is per tab", async () => {
    await cmd(SOCK_PATH, "open", { url: "data:text/html,<h1>B1</h1>" }, "r1", "b");
    // tab "b" has a single history entry, so back must fail there
    const backResp = await cmd(SOCK_PATH, "back", {}, "r1", "b");
    expect(backResp.success).toBe(false);
  });

  it("close releases a named tab and keeps the browser", async () => {
    await cmd(SOCK_PATH, "open", { url: "data:text/html,<h1>C</h1>" }, "r1", "c");
    const resp = await cmd(SOCK_PATH, "close", {}, "r1", "c");
    expect(resp.success).toBe(true);
    // Other tabs (the default one) keep the browser and daemon alive.
    expect((await cmd(SOCK_PATH, "url")).success).toBe(true);
  });

  it("close does not hijack another tab", async () => {
    await cmd(SOCK_PATH, "open", { url: "data:text/html,<title>KEEP</title>" }, "r1", "keep");
    await cmd(SOCK_PATH, "open", { url: "data:text/html,<title>GOING</title>" }, "r1", "going");
    expect((await cmd(SOCK_PATH, "close", {}, "r1", "going")).success).toBe(true);
    // The other agent must still be on its OWN page, not a hijacked one.
    const resp = await cmd(SOCK_PATH, "title", {}, "r1", "keep");
    expect(resp.data.title).toBe("KEEP");
  });

  it("close is idempotent on a page-less tab", async () => {
    // A close from a tab that never opened a page succeeds as a no-op and
    // must not shut down the browser other tabs are using.
    const resp = await cmd(SOCK_PATH, "close", {}, "r1", "never-opened-close");
    expect(resp.success).toBe(true);
    expect((await cmd(SOCK_PATH, "url")).success).toBe(true);
  });

  it("a command on a page-less tab errors instead of returning a blank page", async () => {
    const resp = await cmd(SOCK_PATH, "title", {}, "r1", "never-opened-xyz");
    expect(resp.success).toBe(false);
    expect(resp.error).toContain("no open page");
  });
});

describe("e2e close shuts down daemon", { timeout: 120_000 }, () => {
  it("closing the last tab stops the daemon", async () => {
    const session = `e2e-close-${process.pid}-${Date.now()}`;
    const sockPath = `/tmp/camoufox-cli-${session}.sock`;
    const server = new DaemonServer({ session, headless: true, timeout: 60 });
    const promise = server.start();
    await waitForSocket(sockPath);

    const openResp = await sendCommand(sockPath, { id: "r0", action: "open", params: { url: FIXTURE_URL } });
    expect(openResp.success).toBe(true);

    // The default tab is the only live tab, so this close takes the
    // browser — and with it the daemon — down.
    const resp = await sendCommand(sockPath, { id: "r1", action: "close", params: {} });
    expect(resp.success).toBe(true);

    await promise;
    expect(fs.existsSync(sockPath)).toBe(false);
  });
});
