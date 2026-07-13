/** Unix socket server for the camoufox-cli daemon. */

import * as net from "node:net";
import * as fs from "node:fs";
import { BrowserManager } from "./browser.js";
import { execute } from "./commands.js";
import { parseCommand, serializeResponse } from "./protocol.js";

export class DaemonServer {
  private session: string;
  private headless: boolean;
  private timeout: number;
  private socketPath: string;
  private pidPath: string;
  private manager: BrowserManager;
  private server: net.Server | null = null;
  private lastActivity = Date.now();
  private watchdogTimer: ReturnType<typeof setInterval> | null = null;
  // The server runs with allowHalfOpen, so a client that half-closes leaves
  // the server side lingering until we destroy it. Track live connections so
  // shutdown can drop them — otherwise server.close() never emits 'close'.
  private connections = new Set<net.Socket>();

  constructor(opts: { session?: string; headless?: boolean; timeout?: number; persistent?: string | null; proxy?: string | null; geoip?: boolean; locale?: string | null }) {
    this.session = opts.session ?? "default";
    this.headless = opts.headless ?? true;
    this.timeout = opts.timeout ?? 1800;
    this.socketPath = `/tmp/camoufox-cli-${this.session}.sock`;
    this.pidPath = `/tmp/camoufox-cli-${this.session}.pid`;
    this.manager = new BrowserManager(opts.persistent ?? null, opts.proxy ?? null, opts.geoip ?? true, opts.locale ?? null);
  }

  async start(): Promise<void> {
    this.cleanupStale();
    this.writePid();
    // Idle timeout watchdog
    this.watchdogTimer = setInterval(() => {
      if (Date.now() - this.lastActivity > this.timeout * 1000) {
        process.stderr.write(`[camoufox-cli] Idle timeout (${this.timeout}s), shutting down\n`);
        this.closeServer();
      }
    }, 10000);

    // Signal handlers
    process.on("SIGTERM", () => { this.closeServer(); });
    process.on("SIGINT", () => { this.closeServer(); });

    this.server = net.createServer({ allowHalfOpen: true }, (conn) => this.handleConnection(conn));

    await new Promise<void>((resolve, reject) => {
      this.server!.listen(this.socketPath, () => resolve());
      this.server!.on("error", reject);
    });

    process.stderr.write(`[camoufox-cli] Daemon listening session=${this.session}\n`);

    // Wait until server closes
    await new Promise<void>((resolve) => {
      this.server!.on("close", resolve);
    });

    await this.shutdown();
  }

  private handleConnection(conn: net.Socket): void {
    this.connections.add(conn);
    conn.on("close", () => this.connections.delete(conn));

    let data = "";
    let handled = false;

    const processData = async () => {
      if (handled) return;
      const nlIdx = data.indexOf("\n");
      if (nlIdx < 0) return;
      handled = true;

      this.lastActivity = Date.now();
      const line = data.slice(0, nlIdx).trim();
      if (!line) { conn.destroy(); return; }

      try {
        const command = parseCommand(line);

        if (command.action === "open") {
          command.params.headless ??= this.headless;
        }

        const response = await execute(this.manager, command as any);
        conn.end(serializeResponse(response));

        if (command.action === "close") {
          // Destroy the current connection only after its response has
          // flushed, then drop the rest via closeServer().
          conn.once("finish", () => conn.destroy());
          this.closeServer(conn);
        }
      } catch (e: any) {
        conn.end(Buffer.from(JSON.stringify({ id: "?", success: false, error: String(e) }) + "\n"));
      }
    };

    conn.on("data", (chunk) => {
      data += chunk.toString();
      processData();
    });

    conn.on("end", () => { processData(); });
  }

  private cleanupStale(): void {
    if (fs.existsSync(this.socketPath)) {
      if (fs.existsSync(this.pidPath)) {
        try {
          const pid = parseInt(fs.readFileSync(this.pidPath, "utf-8").trim(), 10);
          process.kill(pid, 0); // Check if alive
          process.stderr.write(`[camoufox-cli] Daemon already running (pid ${pid})\n`);
          process.exit(1);
        } catch {
          // Stale pid, clean up
        }
      }
      fs.unlinkSync(this.socketPath);
    }
  }

  private writePid(): void {
    fs.writeFileSync(this.pidPath, String(process.pid));
  }

  /**
   * Stop the server and drop every lingering half-open connection so it can
   * actually emit 'close'. Without destroying connections, allowHalfOpen keeps
   * them alive and server.close() never completes, so the daemon hangs forever.
   * Pass `except` to spare one connection (e.g. the in-flight close command,
   * which destroys itself once its response has flushed).
   */
  private closeServer(except?: net.Socket): void {
    this.server?.close();
    for (const c of this.connections) {
      if (c !== except) c.destroy();
    }
  }

  private async shutdown(): Promise<void> {
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    await this.manager.close();
    this.closeServer();
    for (const p of [this.socketPath, this.pidPath]) {
      try { fs.unlinkSync(p); } catch {}
    }
  }
}
