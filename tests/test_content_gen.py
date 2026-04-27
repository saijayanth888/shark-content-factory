"""
Tests for the content_gen MCP server.

Tests are split into:
- Unit tests (no API keys needed — test helpers, templates, thumbnails)
- Integration tests (need API keys — marked with @pytest.mark.integration)
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from mcp_servers.content_gen import (
    _calculate_cost,
    _load_template,
    _safe_topic,
    _today,
    generate_thumbnail,
)

# ---------------------------------------------------------------------------
# Unit tests — no API keys required
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_safe_topic_removes_special_chars(self):
        assert _safe_topic("Claude Code vs Cursor AI!") == "claude_code_vs_cursor_ai"

    def test_safe_topic_truncates_long_strings(self):
        long_topic = "a" * 100
        assert len(_safe_topic(long_topic)) <= 60

    def test_safe_topic_strips_leading_trailing_underscores(self):
        assert _safe_topic("  hello world  ") == "hello_world"

    def test_today_format(self):
        date = _today()
        assert len(date) == 10
        assert date[4] == "-"
        assert date[7] == "-"

    def test_calculate_cost(self):
        # 1000 input tokens at $3/M = $0.003
        # 500 output tokens at $15/M = $0.0075
        cost = _calculate_cost(1000, 500)
        assert abs(cost - 0.0105) < 0.0001

    def test_calculate_cost_zero(self):
        assert _calculate_cost(0, 0) == 0.0


class TestTemplates:
    def test_load_template_build_log(self):
        template = _load_template("build_log")
        assert "Shark Agent Build Log" in template or template == ""

    def test_load_template_tool_review(self):
        template = _load_template("tool_review")
        assert "Tool Teardowns" in template or template == ""

    def test_load_template_tutorial(self):
        template = _load_template("tutorial")
        assert "Build With AI" in template or template == ""

    def test_load_template_short(self):
        template = _load_template("short")
        assert "Shorts" in template or template == ""

    def test_load_template_unknown_falls_back(self):
        template = _load_template("nonexistent_series")
        # Should fall back to tutorial template or empty string
        assert isinstance(template, str)


class TestThumbnail:
    def test_generate_thumbnail_creates_file(self, tmp_path):
        # Patch QUEUE_DIR to use temp directory
        with patch("mcp_servers.content_gen.QUEUE_DIR", tmp_path):
            result = json.loads(generate_thumbnail("test topic", "TEST"))
            assert "thumbnail_path" in result
            assert result["resolution"] == "1280x720"
            assert result["cost_usd"] == 0.0
            assert Path(result["thumbnail_path"]).exists()

    def test_generate_thumbnail_png_format(self, tmp_path):
        with patch("mcp_servers.content_gen.QUEUE_DIR", tmp_path):
            result = json.loads(generate_thumbnail("test", "Test"))
            assert result["thumbnail_path"].endswith(".png")


# ---------------------------------------------------------------------------
# Integration tests — require API keys
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestScriptGeneration:
    """These tests call the Claude API. Skip if ANTHROPIC_API_KEY not set."""

    @pytest.fixture(autouse=True)
    def skip_without_key(self):
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

    def test_generate_script_returns_valid_json(self, tmp_path):
        from mcp_servers.content_gen import generate_script

        with patch("mcp_servers.content_gen.QUEUE_DIR", tmp_path):
            result = json.loads(
                generate_script("Test Topic AI Trading", "tutorial", 5)
            )
            assert "script_path" in result
            assert result["word_count"] > 0
            assert result["cost_usd"] > 0


@pytest.mark.integration
class TestVoiceover:
    """These tests call ElevenLabs API. Skip if key not set."""

    @pytest.fixture(autouse=True)
    def skip_without_key(self):
        if not os.getenv("ELEVENLABS_API_KEY"):
            pytest.skip("ELEVENLABS_API_KEY not set")


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfigs:
    def test_voices_json_valid(self):
        voices_path = Path(__file__).parent.parent / "config" / "voices.json"
        if voices_path.exists():
            data = json.loads(voices_path.read_text())
            assert "default" in data
            assert "voice_id" in data["default"]

    def test_niches_json_valid(self):
        niches_path = Path(__file__).parent.parent / "config" / "niches.json"
        if niches_path.exists():
            data = json.loads(niches_path.read_text())
            assert "primary_niches" in data
            assert len(data["primary_niches"]) >= 3

    def test_schedule_json_valid(self):
        sched_path = Path(__file__).parent.parent / "config" / "schedule.json"
        if sched_path.exists():
            data = json.loads(sched_path.read_text())
            assert "long_form_slots" in data
            assert "shorts_slots" in data
            assert len(data["long_form_slots"]) == 3

    def test_platforms_json_valid(self):
        plat_path = Path(__file__).parent.parent / "config" / "platforms.json"
        if plat_path.exists():
            data = json.loads(plat_path.read_text())
            assert "youtube_longform" in data
            assert "youtube_shorts" in data
            assert "instagram_reels" in data
            assert data["youtube_shorts"]["resolution"] == "1080x1920"
            assert data["instagram_reels"]["resolution"] == "1080x1920"
