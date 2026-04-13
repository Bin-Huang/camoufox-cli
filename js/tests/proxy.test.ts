import { describe, expect, it } from "vitest";
import { parseProxySettings } from "../src/proxy.js";

describe("parseProxySettings", () => {
  it("parses an HTTP proxy without credentials", () => {
    expect(parseProxySettings("http://host:8080")).toEqual({
      proxy: {
        server: "http://host:8080",
      },
    });
  });

  it("returns credentials for authenticated HTTP proxies", () => {
    expect(parseProxySettings("http://user:pass@host:8080")).toEqual({
      proxy: {
        server: "http://host:8080",
        username: "user",
        password: "pass",
      },
    });
  });

  it("decodes percent-encoded credentials", () => {
    expect(parseProxySettings("http://user%40x:pass%2Fword@host:8080")).toEqual({
      proxy: {
        server: "http://host:8080",
        username: "user@x",
        password: "pass/word",
      },
    });
  });

  it("rejects https:// scheme with a clear error", () => {
    expect(() => parseProxySettings("https://user:pass@host:443")).toThrow(
      /Only http:\/\//
    );
  });
});
