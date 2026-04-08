import { describe, it, expect, afterEach } from "vitest";
import * as net from "node:net";
import * as fs from "node:fs";
import { DaemonServer } from "../src/server.js";
import { getPidPath, getSocketPath, isFilesystemSocketPath } from "../src/ipc.js";

async function waitForServer(sockPath: string, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await new Promise<boolean>((resolve) => {
      const client = net.createConnection(sockPath, () => {
        client.destroy();
        resolve(true);
      });
      client.on("error", () => resolve(false));
    });

    if (ready) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  throw new Error(`Server ${sockPath} not ready after ${timeoutMs}ms`);
}

function getPaths(session: string) {
  return {
    sockPath: getSocketPath(session),
    pidPath: getPidPath(session),
  };
}

function cleanup(session: string) {
  const { sockPath, pidPath } = getPaths(session);
  try { fs.unlinkSync(pidPath); } catch {}
  if (isFilesystemSocketPath(sockPath)) {
    try { fs.unlinkSync(sockPath); } catch {}
  }
}

describe("DaemonServer", () => {
  let lastSession: string | null = null;

  afterEach(() => {
    if (lastSession) {
      cleanup(lastSession);
      lastSession = null;
    }
  });

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
    const session = `test-start-${process.pid}-${Date.now()}`;
    lastSession = session;
    const { sockPath } = getPaths(session);
    const server = new DaemonServer({
      session,
      timeout: 5,
    });

    // Start server in background
    const serverPromise = server.start();

    await waitForServer(sockPath);

    // Send close command to shut down
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(sockPath, () => {
        client.write(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
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
    const session = `test-pid-${process.pid}-${Date.now()}`;
    lastSession = session;
    const { sockPath, pidPath } = getPaths(session);
    const server = new DaemonServer({
      session,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(pidPath)) break;
      await new Promise(r => setTimeout(r, 100));
    }
    expect(fs.existsSync(pidPath)).toBe(true);

    const pid = fs.readFileSync(pidPath, "utf-8").trim();
    expect(parseInt(pid, 10)).toBe(process.pid);

    // Clean shutdown
    const client = net.createConnection(sockPath, () => {
      client.write(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;
  });

  it("handles unknown actions gracefully", async () => {
    const session = `test-unknown-${process.pid}-${Date.now()}`;
    lastSession = session;
    const { sockPath } = getPaths(session);
    const server = new DaemonServer({
      session,
      timeout: 5,
    });

    const serverPromise = server.start();

    await waitForServer(sockPath);

    // Send unknown action
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(sockPath, () => {
        client.write(JSON.stringify({ id: "r1", action: "nonexistent", params: {} }) + "\n");
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
      const client = net.createConnection(sockPath, () => {
        client.write(JSON.stringify({ id: "r2", action: "close", params: {} }) + "\n");
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
    const session = `test-invalid-${process.pid}-${Date.now()}`;
    lastSession = session;
    const { sockPath } = getPaths(session);
    const server = new DaemonServer({
      session,
      timeout: 5,
    });

    const serverPromise = server.start();

    await waitForServer(sockPath);

    // Send invalid JSON
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(sockPath, () => {
        client.write("not valid json\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(false);

    // Shut down
    const client = net.createConnection(sockPath, () => {
      client.write(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;
  });

  it("cleans up socket and pid on shutdown", async () => {
    const session = `test-cleanup-${process.pid}-${Date.now()}`;
    lastSession = session;
    const { sockPath, pidPath } = getPaths(session);
    const server = new DaemonServer({
      session,
      timeout: 5,
    });

    const serverPromise = server.start();

    await waitForServer(sockPath);

    // Shut down
    const client = net.createConnection(sockPath, () => {
      client.write(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;

    // Files should be cleaned up
    expect(fs.existsSync(pidPath)).toBe(false);
    if (isFilesystemSocketPath(sockPath)) {
      expect(fs.existsSync(sockPath)).toBe(false);
    }
  });
});
