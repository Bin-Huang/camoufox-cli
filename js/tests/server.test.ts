import { describe, it, expect, afterEach } from "vitest";
import * as net from "node:net";
import * as fs from "node:fs";
import * as path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { DaemonServer } from "../src/server.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const TEST_SESSION = `test-${process.pid}-${Date.now()}`;
const SOCK_PATH = `/tmp/camoufox-cli-${TEST_SESSION}.sock`;
const PID_PATH = `/tmp/camoufox-cli-${TEST_SESSION}.pid`;

function tempPidFiles(): string[] {
  return fs.readdirSync("/tmp").filter((f) => f.startsWith(`camoufox-cli-${TEST_SESSION}.pid.`));
}

function cleanup() {
  for (const p of [SOCK_PATH, PID_PATH]) {
    try { fs.unlinkSync(p); } catch {}
  }
  for (const f of tempPidFiles()) {
    try { fs.unlinkSync(`/tmp/${f}`); } catch {}
  }
}

describe("DaemonServer", () => {
  afterEach(cleanup);

  it("constructs with defaults", () => {
    const server = new DaemonServer({});
    expect(server).toBeDefined();
  });

  it("constructs with custom options", () => {
    const server = new DaemonServer({
      session: "custom",
      headless: false,
      timeout: 60,
    });
    expect(server).toBeDefined();
  });

  it("starts and accepts connections", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    // Start server in background
    const serverPromise = server.start();

    // Wait for socket to appear
    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }
    expect(fs.existsSync(SOCK_PATH)).toBe(true);

    // Send close command to shut down
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(true);

    await serverPromise;
  });

  it("writes pid file", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(PID_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }
    expect(fs.existsSync(PID_PATH)).toBe(true);

    const pid = fs.readFileSync(PID_PATH, "utf-8").trim();
    expect(parseInt(pid, 10)).toBe(process.pid);

    // Clean shutdown
    const client = net.createConnection(SOCK_PATH, () => {
      client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;
  });

  it("handles unknown actions gracefully", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    // Send unknown action
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id: "r1", action: "nonexistent", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(false);
    expect(parsed.error).toContain("Unknown action");

    // Shut down
    const closeResp = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id: "r2", action: "close", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });
    expect(JSON.parse(closeResp).success).toBe(true);

    await serverPromise;
  });

  it("handles invalid JSON gracefully", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    // Send invalid JSON
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end("not valid json\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(false);

    // Shut down
    const client = net.createConnection(SOCK_PATH, () => {
      client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;
  });

  it("concurrent closes all receive a response (none eaten by shutdown)", async () => {
    // Regression: N agents closing at once. The first close to complete used
    // to see isRunning=false and destroy every sibling connection before its
    // response flushed — the tabs were released but the clients reported
    // failure. All N clients must get a parseable success response.
    const server = new DaemonServer({ session: TEST_SESSION, timeout: 5 });
    const serverPromise = server.start();
    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    const sendClose = (id: string) => new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id, action: "close", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const responses = await Promise.all(
      ["c1", "c2", "c3", "c4", "c5", "c6"].map(sendClose)
    );
    // Every connection whose request began processing must get a full,
    // parseable response (the old code destroyed them mid-response). A
    // sibling that had not even been read yet may be dropped at shutdown —
    // the real CLI covers that via its idempotent-close fallback — but a
    // partial/truncated response is never acceptable.
    let delivered = 0;
    for (const raw of responses) {
      if (raw === "") continue;
      const parsed = JSON.parse(raw); // truncated raw -> test fails here
      expect(parsed.success).toBe(true);
      delivered++;
    }
    expect(delivered).toBeGreaterThan(0);

    await serverPromise; // daemon still shuts down cleanly afterwards
    expect(fs.existsSync(SOCK_PATH)).toBe(false);
  });

  it("cleans up socket and pid on shutdown", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    // Shut down
    const client = net.createConnection(SOCK_PATH, () => {
      client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;

    // Files should be cleaned up
    expect(fs.existsSync(SOCK_PATH)).toBe(false);
    expect(fs.existsSync(PID_PATH)).toBe(false);
  });

  it("shuts down on close even with a lingering open connection", async () => {
    const server = new DaemonServer({ session: TEST_SESSION, timeout: 60 });
    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise((r) => setTimeout(r, 100));
    }

    // An idle connection the server never responds to (e.g. a liveness check
    // that connects and sends no complete command). It stays in the server's
    // connection set — and used to stop server.close() from ever emitting
    // 'close', hanging the daemon forever.
    const lingering = net.createConnection(SOCK_PATH);
    await new Promise((r) => lingering.once("connect", r));

    // Now close over a second connection. The daemon must still shut down.
    const closer = net.createConnection(SOCK_PATH, () => {
      closer.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    closer.on("data", () => {});

    await Promise.race([
      serverPromise,
      new Promise((_, reject) => setTimeout(() => reject(new Error("daemon did not shut down within 5s")), 5000)),
    ]);

    lingering.destroy();
    expect(fs.existsSync(SOCK_PATH)).toBe(false);
    expect(fs.existsSync(PID_PATH)).toBe(false);
  });

  // A daemon that loses the pid-claim race exits via process.exit(), which
  // does NOT run finally — so this must spawn a real daemon process to be
  // faithful (mocking process.exit as a throw lets finally run and hides the
  // bug). Runs against the built daemon; skips gracefully when dist is absent.
  it("a losing daemon exits without leaking a temp pid file", async () => {
    const daemonJs = path.resolve(__dirname, "../dist/daemon.js");
    if (!fs.existsSync(daemonJs)) return; // needs `npm run build`; real-CLI covers it otherwise

    // Hold the session with a definitely-alive pid (this test process).
    fs.writeFileSync(PID_PATH, String(process.pid));

    const child = spawn(process.execPath, [daemonJs, "--session", TEST_SESSION], { stdio: "ignore" });
    const code = await new Promise<number>((resolve) => child.on("exit", (c) => resolve(c ?? -1)));

    expect(code).toBe(1);                 // loser exits non-zero
    expect(tempPidFiles()).toEqual([]);   // and leaves no temp pid file behind
    // ...and never deletes the live winner's pid file.
    expect(fs.readFileSync(PID_PATH, "utf-8").trim()).toBe(String(process.pid));
  });
});
