"""Entry point: python -m camoufox_cli"""

import argparse
import sys

from .server import DaemonServer


def main():
    parser = argparse.ArgumentParser(description="camoufox-cli daemon server")
    parser.add_argument("--session", default="default", help="Session name")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--timeout", type=int, default=1800, help="Idle timeout in seconds")
    parser.add_argument("--persistent", default=None, help="Path for persistent browser profile")
    parser.add_argument("--proxy", default=None, help="Proxy server URL")
    parser.add_argument("--no-geoip", dest="geoip", action="store_false", default=True, help="Disable automatic GeoIP spoofing when using a proxy")
    parser.add_argument("--locale", default=None, help="Force browser locale (e.g. 'en-US' or 'en-US,zh-CN')")
    args = parser.parse_args()

    headless = not args.headed

    server = DaemonServer(
        session=args.session,
        headless=headless,
        timeout=args.timeout,
        persistent=args.persistent,
        proxy=args.proxy,
        geoip=args.geoip,
        locale=args.locale,
    )

    print(f"[camoufox-cli] Starting daemon session={args.session} headless={headless}", file=sys.stderr)
    server.start()


if __name__ == "__main__":
    main()
