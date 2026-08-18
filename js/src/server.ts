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
  // The server runs with allowHalfOpen, so a client that half-closes leaves
  // the server side lingering until we destroy it. Track live connections so
  // shutdown can drop them — otherwise server.close() never emits 'close'.
  private connections = new Set<net.Socket>();
  // Connections currently processing a request; closeServer defers their
  // destruction until the response has flushed.
  private busy = new Set<net.Socket>();

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
        this.closeServer();
      }
    }, 10000);

    // Signal handlers
    process.on("SIGTERM", () => { this.closeServer(); });
    process.on("SIGINT", () => { this.closeServer(); });

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
    this.connections.add(conn);
    conn.on("close", () => { this.connections.delete(conn); this.busy.delete(conn); });

    let data = "";
    let handled = false;

    const processData = async () => {
      if (handled) return;
      const nlIdx = data.indexOf("\n");
      if (nlIdx < 0) return;
      handled = true;
      // Mark mid-request: closeServer must let this connection's response
      // flush instead of destroying it (its client would otherwise never
      // learn that its command actually succeeded).
      this.busy.add(conn);

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

        // A close releases the caller's tab; the daemon exits only when that
        // was the last tab (the manager shut the browser down). Other agents'
        // tabs keep the daemon alive, so a non-final close just responds and
        // its connection cleans up on the normal path.
        if (command.action === "close" && !this.manager.isRunning) {
          this.closeServer();
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
   * Claim the session's pid file, or exit.
   *
   * Concurrent clients may each spawn a daemon for the same session. The pid is
   * written to a private temp file first and published with link() — atomic, so
   * the pid file appears with its full content and, in the common case (no prior
   * daemon), exactly one racer wins. Reclaiming a *stale* pid file left by a
   * hard-crashed daemon is best-effort here: Node has no flock(), so we fall
   * back to a liveness check. The Python daemon uses fcntl.flock (which the OS
   * releases on crash) and is fully race-free; this divergence is unavoidable
   * without a native locking addon. In practice the client's connect-retry plus
   * the deep listen backlog keep concurrent respawns rare.
   */
  private claimPid(): void {
    const tmpPath = `${this.pidPath}.${process.pid}`;
    fs.writeFileSync(tmpPath, String(process.pid));
    // process.exit() does NOT run finally blocks, so remove the temp file
    // explicitly before every exit as well as on the normal return path.
    const rmTmp = () => { try { fs.unlinkSync(tmpPath); } catch {} };
    const isErrno = (e: unknown, code: string) => (e as NodeJS.ErrnoException)?.code === code;
    try {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          fs.linkSync(tmpPath, this.pidPath);
        } catch (e) {
          // Surface real filesystem errors instead of misreading them as
          // pid-file contention.
          if (!isErrno(e, "EEXIST")) { rmTmp(); throw e; }
          let pid: number;
          try {
            pid = parseInt(fs.readFileSync(this.pidPath, "utf-8").trim(), 10);
            process.kill(pid, 0); // alive?
          } catch {
            // Stale/foreign pid — clean up and retry the link.
            try { fs.unlinkSync(this.pidPath); } catch {}
            continue;
          }
          process.stderr.write(`[camoufox-cli] Daemon already running (pid ${pid})\n`);
          rmTmp();
          process.exit(1);
        }
        // The session is ours now; clear any leftover socket from a dead daemon.
        try { fs.unlinkSync(this.socketPath); } catch {}
        return;
      }
      process.stderr.write(`[camoufox-cli] Could not claim pid file, another daemon is starting\n`);
      rmTmp();
      process.exit(1);
    } finally {
      rmTmp();
    }
  }

  /**
   * Stop the server and drop lingering connections so it can actually emit
   * 'close'. Without destroying idle half-open connections, allowHalfOpen
   * keeps them alive and server.close() never completes, so the daemon hangs
   * forever. Connections that are mid-request (concurrent commands — e.g.
   * several agents' closes racing the last-tab shutdown) are NOT cut: their
   * work has already executed, so destroying them would eat the response and
   * make the client report a failure for a command that succeeded. They are
   * destroyed once their response flushes ('finish'), with a timeout backstop
   * so a wedged handler can't keep the daemon alive forever.
   */
  private closeServer(): void {
    this.server?.close();
    for (const c of this.connections) {
      if (!this.busy.has(c) || c.writableFinished) {
        c.destroy();
        continue;
      }
      const backstop = setTimeout(() => c.destroy(), 10_000);
      backstop.unref();
      c.once("finish", () => { clearTimeout(backstop); c.destroy(); });
    }
  }

  private async shutdown(): Promise<void> {
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    await this.manager.close();
    this.closeServer();
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
