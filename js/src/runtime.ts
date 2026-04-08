import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

export function getNodeCommand(): string {
  return process.execPath;
}

export function getCamoufoxJsCliPath(): string {
  return require.resolve("camoufox-js/dist/__main__.js");
}
