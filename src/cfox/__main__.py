"""Entry point: python -m cfox.server"""

import argparse
import sys

from .server import DaemonServer


def main():
    parser = argparse.ArgumentParser(description="cfox daemon server")
    parser.add_argument("--session", default="default", help="Session name")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--timeout", type=int, default=1800, help="Idle timeout in seconds")
    parser.add_argument("--persistent", default=None, help="Path for persistent browser profile")
    args = parser.parse_args()

    headless = not args.headed

    server = DaemonServer(
        session=args.session,
        headless=headless,
        timeout=args.timeout,
        persistent=args.persistent,
    )

    print(f"[cfox] Starting daemon session={args.session} headless={headless}", file=sys.stderr)
    server.start()


if __name__ == "__main__":
    main()
