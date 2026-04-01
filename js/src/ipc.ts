import * as os from "node:os";
import * as path from "node:path";

const SESSION_PREFIX = "camoufox-cli-";
const SOCKET_SUFFIX = ".sock";
const PID_SUFFIX = ".pid";
const WINDOWS_PIPE_PREFIX = "\\\\.\\pipe\\";

export function getSocketPath(session: string): string {
  const socketName = `${SESSION_PREFIX}${session}${SOCKET_SUFFIX}`;
  return process.platform === "win32"
    ? `${WINDOWS_PIPE_PREFIX}${socketName}`
    : `/tmp/${socketName}`;
}

export function getPidPath(session: string): string {
  return path.join(os.tmpdir(), `${SESSION_PREFIX}${session}${PID_SUFFIX}`);
}

export function getPidDir(): string {
  return os.tmpdir();
}

export function getSessionFromPidFile(fileName: string): string | null {
  if (!fileName.startsWith(SESSION_PREFIX) || !fileName.endsWith(PID_SUFFIX)) {
    return null;
  }

  return fileName.slice(SESSION_PREFIX.length, -PID_SUFFIX.length);
}

export function isFilesystemSocketPath(socketPath: string): boolean {
  return !socketPath.startsWith(WINDOWS_PIPE_PREFIX);
}
