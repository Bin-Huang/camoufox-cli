import { describe, it, expect } from "vitest";
import * as os from "node:os";
import * as path from "node:path";
import { getPidPath, getSocketPath, isFilesystemSocketPath } from "../src/ipc.js";

describe("ipc paths", () => {
  it("uses a platform-specific socket path", () => {
    expect(getSocketPath("default")).toBe(
      process.platform === "win32"
        ? "\\\\.\\pipe\\camoufox-cli-default.sock"
        : "/tmp/camoufox-cli-default.sock",
    );
  });

  it("stores pid files in the system temp directory", () => {
    expect(getPidPath("default")).toBe(
      path.join(os.tmpdir(), "camoufox-cli-default.pid"),
    );
  });

  it("reports whether the socket uses the filesystem", () => {
    expect(isFilesystemSocketPath(getSocketPath("default"))).toBe(
      process.platform !== "win32",
    );
  });
});
