"""
Tests for the youtube_api MCP server.

Unit tests mock the Google API client.
Integration tests require OAuth credentials.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestUploadVideoMock:
    """Test upload_video with mocked YouTube API."""

    @patch("mcp_servers.youtube_api._get_youtube_service")
    def test_upload_returns_video_id(self, mock_service):
        from mcp_servers.youtube_api import upload_video

        mock_insert = MagicMock()
        mock_insert.next_chunk.return_value = (
            None,
            {"id": "test_video_123"},
        )
        mock_service.return_value.videos.return_value.insert.return_value = mock_insert

        # Create a temp video file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            temp_path = f.name

        try:
            result = json.loads(upload_video(
                video_path=temp_path,
                title="Test Video",
                description="Test description",
                tags=["test", "ai"],
            ))
            assert result["video_id"] == "test_video_123"
            assert "youtube.com" in result["url"]
            assert result["contains_synthetic_media"] is True
        finally:
            os.unlink(temp_path)

    @patch("mcp_servers.youtube_api._get_youtube_service")
    def test_upload_short_adds_hashtag(self, mock_service):
        from mcp_servers.youtube_api import upload_video

        mock_insert = MagicMock()
        mock_insert.next_chunk.return_value = (
            None,
            {"id": "short_123"},
        )
        mock_service.return_value.videos.return_value.insert.return_value = mock_insert

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            temp_path = f.name

        try:
            result = json.loads(upload_video(
                video_path=temp_path,
                title="AI Trading Tip",
                description="Quick tip",
                tags=["ai"],
                is_short=True,
            ))
            assert "#Shorts" in result["title"]
            assert result["is_short"] is True
        finally:
            os.unlink(temp_path)


class TestAnalyticsMock:
    """Test get_channel_analytics with mocked YouTube API."""

    @patch("mcp_servers.youtube_api._get_youtube_service")
    def test_analytics_returns_channel_data(self, mock_service):
        from mcp_servers.youtube_api import get_channel_analytics

        mock_yt = mock_service.return_value

        mock_yt.channels.return_value.list.return_value.execute.return_value = {
            "items": [{
                "snippet": {"title": "SharkWave AI"},
                "statistics": {
                    "subscriberCount": "150",
                    "viewCount": "5000",
                    "videoCount": "10",
                },
            }]
        }

        mock_yt.search.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        result = json.loads(get_channel_analytics(days=7))
        assert result["channel"]["name"] == "SharkWave AI"
        assert result["channel"]["subscribers"] == 150
        assert result["channel"]["total_views"] == 5000


class TestPlaylistMock:
    """Test playlist operations with mocked YouTube API."""

    @patch("mcp_servers.youtube_api._get_youtube_service")
    def test_create_playlist(self, mock_service):
        from mcp_servers.youtube_api import create_playlist

        mock_service.return_value.playlists.return_value.insert.return_value.execute.return_value = {
            "id": "PLtest123"
        }

        result = json.loads(create_playlist("Test Playlist", "A test playlist"))
        assert result["playlist_id"] == "PLtest123"
        assert "youtube.com/playlist" in result["url"]

    @patch("mcp_servers.youtube_api._get_youtube_service")
    def test_add_to_playlist(self, mock_service):
        from mcp_servers.youtube_api import add_to_playlist

        mock_service.return_value.playlistItems.return_value.insert.return_value.execute.return_value = {}

        result = json.loads(add_to_playlist("vid_123", "PL_123"))
        assert result["status"] == "added"


class TestInstagramPublish:
    """Test Instagram publishing (currently returns manual instructions)."""

    def test_publish_without_credentials(self):
        from mcp_servers.youtube_api import publish_to_instagram

        with patch.dict(os.environ, {}, clear=True):
            result = json.loads(
                publish_to_instagram("/tmp/test.mp4", "Test caption #AI")
            )
            # Should gracefully handle missing credentials
            assert "error" in result or "status" in result
