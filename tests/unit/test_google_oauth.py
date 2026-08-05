"""Unit tests for Google OAuth helpers (non-integration)."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from yt_review_queue.google_oauth import (
    DP_SCOPES, YT_SCOPES,
    save_credentials, load_credentials,
    verify_channel,
)


def test_scopes_are_separate():
    """The two scope lists must not be combined (§4.3)."""
    assert DP_SCOPES != YT_SCOPES
    assert "dataportability" in DP_SCOPES[0]
    assert "youtube.readonly" in YT_SCOPES[0]
    assert len(DP_SCOPES) == 1
    assert len(YT_SCOPES) == 1
    # No overlap
    assert set(DP_SCOPES).isdisjoint(set(YT_SCOPES))


def test_save_and_load_credentials(tmp_path):
    """save_credentials writes JSON, load_credentials reads it back."""
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token="test-token",
        refresh_token="test-refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-id",
        client_secret="test-secret",
        scopes=DP_SCOPES,
    )
    filepath = tmp_path / "creds.json"
    save_credentials(creds, filepath)
    assert filepath.exists()

    data = json.loads(filepath.read_text())
    assert data["token"] == "test-token"
    assert data["refresh_token"] == "test-refresh"
    assert data["scopes"] == DP_SCOPES

    loaded = load_credentials(filepath)
    assert loaded.token == "test-token"
    assert loaded.refresh_token == "test-refresh"


def test_verify_channel_with_mock():
    """verify_channel should extract channel_id and title from API response."""
    mock_creds = MagicMock()
    mock_resp = {
        "items": [
            {
                "id": "UC_test123",
                "snippet": {"title": "Test Channel"},
            }
        ]
    }
    with patch("yt_review_queue.google_oauth.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.channels().list().execute.return_value = mock_resp
        result = verify_channel(mock_creds)

    assert result["channel_id"] == "UC_test123"
    assert result["channel_title"] == "Test Channel"


def test_verify_channel_no_items():
    """verify_channel returns Nones when no channel found."""
    mock_creds = MagicMock()
    with patch("yt_review_queue.google_oauth.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.channels().list().execute.return_value = {"items": []}
        result = verify_channel(mock_creds)

    assert result["channel_id"] is None
    assert result["channel_title"] is None


@pytest.mark.skip(reason="requires real Google credentials")
def test_run_data_portability_flow():
    """Integration test — needs real client_secret.json."""
    pass


@pytest.mark.skip(reason="requires real Google credentials")
def test_run_youtube_data_flow():
    """Integration test — needs real client_secret.json."""
    pass
