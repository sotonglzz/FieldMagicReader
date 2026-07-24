"""CLI for Deputy OAuth + timesheet sync.

Usage:
  python sync_deputy.py auth
  python sync_deputy.py sync --from 2025-07-01 --to 2026-06-30
  python sync_deputy.py whoami
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import requests

from deputy import (
    authorization_url,
    deputy_configured,
    exchange_code,
    get_session,
    sync_timesheets,
)


def cmd_auth(_args):
    if not deputy_configured():
        print(
            "Set DEPUTY_CLIENT_ID and DEPUTY_CLIENT_SECRET in .env first "
            "(see .env.example).",
            file=sys.stderr,
        )
        return 1

    url = authorization_url()
    print("1. Open this URL in your browser and approve access:\n")
    print(f"   {url}\n")
    print(
        "2. After login, Deputy redirects to your redirect URI with ?code=...\n"
        "   (If redirect is http://localhost, the browser may show an error page —\n"
        "   that is fine; copy the `code` value from the address bar.)\n"
    )
    code = input("3. Paste the authorization code here: ").strip()
    if not code:
        print("No code provided.", file=sys.stderr)
        return 1
    # Allow pasting a full redirect URL.
    if "code=" in code:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(code if "://" in code else f"http://localhost?{code.lstrip('?')}")
        values = parse_qs(parsed.query).get("code") or []
        code = values[0] if values else code

    tokens = exchange_code(code)
    print("\nAuthorised.")
    print(f"  API base : {tokens.get('api_base')}")
    print(f"  Tokens   : deputy_tokens.json")
    print("\nNext: python sync_deputy.py sync --from YYYY-MM-DD --to YYYY-MM-DD")
    return 0


def cmd_whoami(_args):
    api_base, headers = get_session()
    response = requests.get(f"{api_base}/api/v1/me", headers=headers, timeout=60)
    if not response.ok:
        print(f"WhoAmI failed ({response.status_code}): {response.text}", file=sys.stderr)
        return 1
    data = response.json()
    name = data.get("Name") or data.get("DisplayName") or data.get("Email")
    print(f"OK — authenticated as {name!r} on {api_base}")
    return 0


def cmd_sync(args):
    start = date.fromisoformat(args.start_from)
    end = date.fromisoformat(args.to)
    if end < start:
        print("--to must be on or after --from", file=sys.stderr)
        return 1
    result = sync_timesheets(start, end, db_name=args.db)
    print(
        f"Synced {result['written']} timesheets "
        f"({result['with_roster_comment']} with roster comments) "
        f"into {args.db}"
    )
    return 0


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    parser = argparse.ArgumentParser(description="Deputy OAuth and timesheet sync")
    sub = parser.add_subparsers(dest="command", required=True)

    auth_parser = sub.add_parser("auth", help="One-time OAuth browser login")
    auth_parser.set_defaults(func=cmd_auth)

    whoami_parser = sub.add_parser("whoami", help="Validate stored access token")
    whoami_parser.set_defaults(func=cmd_whoami)

    sync_parser = sub.add_parser("sync", help="Pull timesheets (+ roster notes) into SQLite")
    sync_parser.add_argument("--from", dest="start_from", required=True, help="YYYY-MM-DD")
    sync_parser.add_argument("--to", required=True, help="YYYY-MM-DD")
    sync_parser.add_argument("--db", default="jobs_cache.db", help="SQLite path")
    sync_parser.set_defaults(func=cmd_sync)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
