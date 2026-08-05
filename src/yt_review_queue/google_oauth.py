"""Google OAuth enrollment helpers.

Implements §4.3 (separate grants) and §7.3 (enrollment).

Two independent OAuth flows per Google account:
  - data_portability grant scope: dataportability.myactivity.youtube
  - youtube_data grant scope: youtube.readonly

These scopes must NOT be combined in a single authorization request.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Separate scope lists — never combined (§4.3)
DP_SCOPES = ["https://www.googleapis.com/auth/dataportability.myactivity.youtube"]
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def run_data_portability_flow(client_secret_path: str) -> Credentials:
    """Run the Data Portability OAuth flow in a local browser."""
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, scopes=DP_SCOPES)
    creds = flow.run_local_server(port=0)
    return creds


def run_youtube_data_flow(client_secret_path: str) -> Credentials:
    """Run the YouTube Data API OAuth flow in a local browser."""
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, scopes=YT_SCOPES)
    creds = flow.run_local_server(port=0)
    return creds


def save_credentials(credentials: Credentials, filepath: str | Path) -> None:
    """Save credentials to a JSON file."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_credentials(filepath: str | Path) -> Credentials:
    """Load credentials from a JSON file."""
    path = Path(filepath)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Credentials(**data)


def refresh_if_needed(credentials: Credentials, client_secret_path: str) -> Credentials:
    """Refresh credentials if expired."""
    if credentials.expired and credentials.refresh_token:
        from google.auth.transport.requests import Request as GoogleRequest
        credentials.refresh(GoogleRequest())
    return credentials


def verify_channel(credentials: Credentials) -> dict[str, str | None]:
    """Call channels.list(mine=true) to verify the YouTube channel.

    Returns dict with channel_id and channel_title.
    """
    service = build("youtube", "v3", credentials=credentials)
    resp = service.channels().list(part="id,snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return {"channel_id": None, "channel_title": None}
    item = items[0]
    return {
        "channel_id": item.get("id"),
        "channel_title": item.get("snippet", {}).get("title"),
    }
