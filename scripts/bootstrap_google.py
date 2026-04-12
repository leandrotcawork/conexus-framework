"""Google Calendar OAuth bootstrap. Run once locally to get a refresh token.

Usage:
  uv run python scripts/bootstrap_google.py

Requires GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env.
Opens a browser, completes the OAuth flow, prints the `fly secrets set`
command you need to run.
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    load_dotenv()

    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env", file=sys.stderr)
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8765/"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=8765)

    if not creds.refresh_token:
        print("ERROR: no refresh_token returned. Revoke existing consent and retry.", file=sys.stderr)
        sys.exit(2)

    print()
    print("=" * 60)
    print("SUCCESS — copy the command below and run it:")
    print("=" * 60)
    print()
    print(f"fly secrets set GOOGLE_OAUTH_REFRESH_TOKEN='{creds.refresh_token}'")
    print()


if __name__ == "__main__":
    main()
