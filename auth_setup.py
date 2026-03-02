#!/usr/bin/env python3
"""One-time OAuth2 setup — run this LOCALLY (not on the server).

Usage:
    python auth_setup.py --credentials path/to/credentials.json --token token.json

This opens a browser, walks through Google's consent screen, and writes the
resulting token to the file you specify.  Copy that token file to the server
afterwards.  The main notifier will refresh it automatically from then on.
"""

import argparse
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials",
        default="credentials.json",
        help="Path to OAuth client secrets JSON from Google Cloud Console. (default: credentials.json)",
    )
    parser.add_argument(
        "--token",
        default="token.json",
        help="Path where the resulting token will be written. (default: token.json)",
    )
    args = parser.parse_args()

    credentials_path = Path(args.credentials)
    token_path = Path(args.token)

    if not credentials_path.exists():
        print(f"Error: credentials file not found at {credentials_path}", file=sys.stderr)
        print(
            "\nDownload it from: Google Cloud Console → APIs & Services → Credentials\n"
            "→ your OAuth 2.0 Client ID → Download JSON",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Opening browser for Google OAuth consent…")
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json())
    print(f"\nToken written to: {token_path}")
    print("\nNext step: copy this file to your server, e.g.:")
    print(f"  scp {token_path} user@your-droplet:/opt/email-notifier/token.json")


if __name__ == "__main__":
    main()
