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
  private bound = false;

  constructor(opts: { session?: string; headless?: boolean; timeout?: number; persistent?: string | null; proxy?: string | null; geoip?: boolean; locale?: string | null }) {
    this.session = opts.session ?? "default";
    this.headless = opts.headless ?? true;
    this.timeout = opts.timeout ?? 1800;
    this.socketPath = `/tmp/camoufox-cli-${this.session}.sock`;
    this.pidPath = `/tmp/camoufox-cli-${this.session}.pid`;
    this.manager = new BrowserManager(opts.persistent ?? null, opts.proxy ?? null, opts.geoip ?? true, opts.locale ?? null);
  }

  async start(): Promise<void> {
    this.claimPid();
    // Idle timeout watchdog
    this.watchdogTimer = setInterval(() => {
      if (Date.now() - this.lastActivity > this.timeout * 1000) {
        process.stderr.write(`[camoufox-cli] Idle timeout (${this.timeout}s), shutting down\n`);
        this.server?.close();
      }
    }, 10000);

    // Signal handlers
    process.on("SIGTERM", () => { this.server?.close(); });
    process.on("SIGINT", () => { this.server?.close(); });

    this.server = net.createServer({ allowHalfOpen: true }, (conn) => this.handleConnection(conn));

    try {
      await new Promise<void>((resolve, reject) => {
        this.server!.listen(this.socketPath, () => resolve());
        this.server!.on("error", reject);
      });
      this.bound = true;

      process.stderr.write(`[camoufox-cli] Daemon listening session=${this.session}\n`);

      // Wait until server closes
      await new Promise<void>((resolve) => {
        this.server!.on("close", resolve);
      });
    } finally {
      await this.shutdown();
    }
  }

  private handleConnection(conn: net.Socket): void {
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
          this.server?.close();
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

  /**
   * Atomically claim the session's pid file, or exit.
   *
   * Concurrent clients may each spawn a daemon for the same session.
   * The pid is written to a private temp file first and published with
   * link(), so the pid file atomically appears with its full content
   * (a create-then-write would let a racer read an empty file, mistake
   * the winner for stale, and delete its files). Exactly one daemon
   * wins; losers exit without touching the winner's files.
   */
  private claimPid(): void {
    const tmpPath = `${this.pidPath}.${process.pid}`;
    fs.writeFileSync(tmpPath, String(process.pid));
    try {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          fs.linkSync(tmpPath, this.pidPath);
          // The session is ours now; clear any leftover socket from a dead daemon.
          try { fs.unlinkSync(this.socketPath); } catch {}
          return;
        } catch {
          try {
            const pid = parseInt(fs.readFileSync(this.pidPath, "utf-8").trim(), 10);
            process.kill(pid, 0); // Check if alive
            process.stderr.write(`[camoufox-cli] Daemon already running (pid ${pid})\n`);
            process.exit(1);
          } catch {
            // Stale pid, clean up and retry
            try { fs.unlinkSync(this.pidPath); } catch {}
          }
        }
      }
      process.stderr.write(`[camoufox-cli] Could not claim pid file, another daemon is starting\n`);
      process.exit(1);
    } finally {
      try { fs.unlinkSync(tmpPath); } catch {}
    }
  }

  private async shutdown(): Promise<void> {
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    await this.manager.close();
    if (this.server) {
      try { this.server.close(); } catch {}
    }
    // Remove only the files this daemon owns, so a losing daemon
    // (bind failure, race) never deletes the live daemon's socket/pid.
    if (this.bound) {
      try { fs.unlinkSync(this.socketPath); } catch {}
    }
    try {
      if (fs.readFileSync(this.pidPath, "utf-8").trim() === String(process.pid)) {
        fs.unlinkSync(this.pidPath);
      }
    } catch {}
  }
}
