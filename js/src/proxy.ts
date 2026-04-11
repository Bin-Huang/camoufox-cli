export interface ProxySettings {
  proxy: {
    server: string;
    username?: string;
    password?: string;
  };
}

export function parseProxySettings(proxyUrl: string): ProxySettings {
  if (!proxyUrl.includes("://")) {
    throw new Error(
      `Invalid proxy URL: ${proxyUrl}. Expected format: http://host:port`
    );
  }

  const parsed = new URL(proxyUrl);
  const scheme = parsed.protocol.slice(0, -1).toLowerCase();
  if (scheme !== "http") {
    throw new Error(
      `Unsupported proxy scheme: ${scheme}. Only http:// proxies are supported.`
    );
  }
  if (!parsed.hostname) {
    throw new Error(
      `Invalid proxy URL: ${proxyUrl}. Expected format: http://host:port`
    );
  }

  const hostPort = parsed.port ? `${parsed.hostname}:${parsed.port}` : parsed.hostname;
  const proxy: ProxySettings["proxy"] = { server: `http://${hostPort}` };
  const username = parsed.username ? decodeURIComponent(parsed.username) : "";
  const password = parsed.password ? decodeURIComponent(parsed.password) : "";

  if (parsed.username) {
    proxy.username = username;
    proxy.password = password;
  }

  return { proxy };
}
