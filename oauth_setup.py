"""
Shark Content Factory — Google OAuth Setup

Run this ONCE to authorize YouTube, Gmail, Sheets, and Drive access.
Stores the token at YOUTUBE_TOKEN_PATH for reuse by MCP servers.

Usage:
    python oauth_setup.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

# --- Load scopes from centralized config ---
_CONFIG_DIR = Path(__file__).parent / "config"
_URLS_PATH = _CONFIG_DIR / "urls.json"
_URL_CONFIG = json.loads(_URLS_PATH.read_text()) if _URLS_PATH.exists() else {}
SCOPES = _URL_CONFIG.get("google_oauth_scopes", [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
])
GOOGLE_CLOUD_CONSOLE_URL = _URL_CONFIG.get("references", {}).get(
    "google_cloud_console", "https://console.cloud.google.com/"
)


def main():
    secrets_path = os.path.expanduser(
        os.getenv(
            "YOUTUBE_CLIENT_SECRETS_PATH",
            "~/.shark-content-factory/client_secrets.json",
        )
    )
    token_path = os.path.expanduser(
        os.getenv(
            "YOUTUBE_TOKEN_PATH",
            "~/.shark-content-factory/youtube_token.json",
        )
    )

    if not os.path.exists(secrets_path):
        print("=" * 60)
        print("ERROR: client_secrets.json not found!")
        print(f"Expected at: {secrets_path}")
        print("=" * 60)
        print()
        print("To set up Google OAuth credentials:")
        print()
        print(f"1. Go to {GOOGLE_CLOUD_CONSOLE_URL}")
        print("2. Create a new project (or select existing)")
        print("3. Enable these APIs:")
        print("   - YouTube Data API v3")
        print("   - Gmail API")
        print("   - Google Sheets API")
        print("   - Google Drive API")
        print("4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID")
        print("5. Application type: Desktop app")
        print("6. Download the JSON file")
        print(f"7. Save it as: {secrets_path}")
        print()
        print("Then run this script again.")
        sys.exit(1)

    # Ensure token directory exists
    Path(token_path).parent.mkdir(parents=True, exist_ok=True)

    print("Starting OAuth authorization flow...")
    print(f"Scopes: {', '.join(s.split('/')[-1] for s in SCOPES)}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
    credentials = flow.run_local_server(port=8080)

    Path(token_path).write_text(credentials.to_json())

    print()
    print("=" * 60)
    print("SUCCESS! OAuth token saved.")
    print(f"Token location: {token_path}")
    print()
    print("Authorized services:")
    print("  - YouTube (upload, manage, analytics)")
    print("  - Gmail (send notifications)")
    print("  - Google Sheets (cost & publish tracking)")
    print("  - Google Drive (reports & documentation)")
    print()
    print("You can now run the content factory.")
    print("=" * 60)


if __name__ == "__main__":
    main()
