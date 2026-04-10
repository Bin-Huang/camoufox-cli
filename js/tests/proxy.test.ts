import { describe, expect, it } from "vitest";
import { parseProxySettings } from "../src/proxy.js";

describe("parseProxySettings", () => {
  it("keeps authenticated HTTPS proxy credentials without extra request headers", () => {
    expect(parseProxySettings("https://user:pass@host:443")).toEqual({
      proxy: {
        server: "https://host",
        username: "user",
        password: "pass",
      },
    });
  });

  it("does not add extra headers for authenticated HTTP proxies", () => {
    expect(parseProxySettings("http://user:pass@host:8080")).toEqual({
      proxy: {
        server: "http://host:8080",
        username: "user",
        password: "pass",
      },
    });
  });

  it("decodes percent-encoded credentials", () => {
    expect(parseProxySettings("https://user%40x:pass%2Fword@host:443")).toEqual({
      proxy: {
        server: "https://host",
        username: "user@x",
        password: "pass/word",
      },
    });
  });
});
