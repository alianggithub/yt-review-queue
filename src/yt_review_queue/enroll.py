"""Enrollment CLI — enroll a Google account into the review queue.

Usage:
    python -m yt_review_queue.enroll <account_label> <client_secret_path>

This runs two separate OAuth flows (§4.3) and verifies the YouTube channel (§7.3).
"""
from __future__ import annotations

import sys
from pathlib import Path

from .google_oauth import (
    run_data_portability_flow,
    run_youtube_data_flow,
    save_credentials,
    verify_channel,
)


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m yt_review_queue.enroll <account_label> <client_secret_path>")
        print()
        print("Steps before running this:")
        print("  1. Enable Data Portability API and YouTube Data API v3 in Google Cloud Console")
        print("  2. Create an OAuth 2.0 Desktop client ID at:")
        print("     https://console.cloud.google.com/apis/credentials")
        print("  3. Download the client_secret JSON file")
        print("  4. Run this command")
        sys.exit(2)

    label = sys.argv[1]
    client_secret = sys.argv[2]

    if not Path(client_secret).exists():
        print(f"ERROR: client secret file not found: {client_secret}")
        sys.exit(1)

    cred_dir = Path("var") / "credentials"
    dp_path = cred_dir / f"{label}_dp.json"
    yt_path = cred_dir / f"{label}_yt.json"

    print(f"Enrolling account '{label}'...")
    print()

    # 1. Data Portability flow
    print("Step 1: Data Portability OAuth (scope: myactivity.youtube)")
    try:
        dp_creds = run_data_portability_flow(client_secret)
    except Exception as e:
        print(f"  ERROR: Data Portability flow failed: {e}")
        print("  If your browser didn't open, ensure you're running on a machine with a display.")
        sys.exit(1)
    save_credentials(dp_creds, dp_path)
    print(f"  Credentials saved to {dp_path}")
    print()

    # 2. YouTube Data API flow
    print("Step 2: YouTube Data OAuth (scope: youtube.readonly)")
    try:
        yt_creds = run_youtube_data_flow(client_secret)
    except Exception as e:
        print(f"  ERROR: YouTube Data flow failed: {e}")
        sys.exit(1)
    save_credentials(yt_creds, yt_path)
    print(f"  Credentials saved to {yt_path}")
    print()

    # 3. Channel verification
    print("Step 3: Verifying YouTube channel...")
    try:
        channel = verify_channel(yt_creds)
    except Exception as e:
        print(f"  ERROR: Channel verification failed: {e}")
        sys.exit(1)

    if channel["channel_id"]:
        print(f"  Account '{label}' enrolled.")
        print(f"  Channel: {channel['channel_title']} ({channel['channel_id']})")
    else:
        print(f"  WARNING: No channel found for this account.")
    print()
    print(f"Credentials:")
    print(f"  Data Portability: {dp_path}")
    print(f"  YouTube Data:     {yt_path}")


if __name__ == "__main__":
    main()
