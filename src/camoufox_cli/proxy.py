"""Proxy parsing helpers shared by browser launch code and tests."""

from __future__ import annotations

from urllib.parse import unquote, urlparse


def parse_proxy_settings(proxy_url: str) -> dict[str, str]:
    parsed = urlparse(proxy_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Unsupported proxy scheme: {parsed.scheme}. Only http:// and https:// proxies are supported."
        )
    if not parsed.hostname:
        raise ValueError(
            f"Invalid proxy URL: {proxy_url}. Expected format: {parsed.scheme}://host:port"
        )

    host_port = parsed.hostname
    if parsed.port:
        host_port += f":{parsed.port}"

    proxy = {"server": f"{parsed.scheme}://{host_port}"}
    username = unquote(parsed.username) if parsed.username is not None else None
    password = unquote(parsed.password) if parsed.password is not None else ""
    if username is not None:
        proxy["username"] = username
        proxy["password"] = password

    return proxy
