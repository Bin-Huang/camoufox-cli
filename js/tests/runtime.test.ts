import { describe, it, expect } from "vitest";
import * as fs from "node:fs";
import { getCamoufoxJsCliPath, getNodeCommand } from "../src/runtime.js";

describe("runtime helpers", () => {
  it("resolves the bundled camoufox-js cli entry", () => {
    expect(fs.existsSync(getCamoufoxJsCliPath())).toBe(true);
  });

  it("uses the current node executable", () => {
    expect(getNodeCommand()).toBe(process.execPath);
  });
});
