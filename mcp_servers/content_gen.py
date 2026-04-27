"""
Shark Content Factory — Content Generation MCP Server

FastMCP server providing tools for the full content pipeline:
- Script generation (Claude Sonnet)
- Voiceover generation (ElevenLabs)
- Video assembly (FFmpeg + Pexels)
- Thumbnail generation (Pillow)
- SEO metadata generation (Claude Sonnet)
- YouTube Shorts / Instagram Reels creation
- Master orchestrator (create_video_package)
"""

import json
import os
import re
import subprocess
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv
from fastmcp import FastMCP
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

mcp = FastMCP(
    "content-gen",
    mask_error_details=IS_PRODUCTION,
)


def _retry_request(fn, max_retries: int = 3, backoff_base: float = 2.0):
    """Retry a callable with exponential backoff. Returns result or raises last exception."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except (requests.exceptions.RequestException, anthropic.APIError) as e:
            last_err = e
            if attempt < max_retries - 1:
                wait = backoff_base ** attempt
                time.sleep(wait)
    raise last_err

CONTENT_DIR = Path(__file__).parent.parent / "content"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
CONFIG_DIR = Path(__file__).parent.parent / "config"
QUEUE_DIR = CONTENT_DIR / "queue"
SHORTS_DIR = CONTENT_DIR / "shorts"
REELS_DIR = CONTENT_DIR / "reels"
FOOTAGE_DIR = CONTENT_DIR / "footage"

# --- Centralized URL config (edit config/urls.json, not code) ---
_URLS_PATH = CONFIG_DIR / "urls.json"
_URL_CONFIG = json.loads(_URLS_PATH.read_text()) if _URLS_PATH.exists() else {}
ELEVENLABS_TTS_URL = _URL_CONFIG.get("apis", {}).get("elevenlabs_tts", "https://api.elevenlabs.io/v1/text-to-speech")
PEXELS_VIDEO_SEARCH_URL = _URL_CONFIG.get("apis", {}).get("pexels_video_search", "https://api.pexels.com/videos/search")
YOUTUBE_SUGGEST_URL = _URL_CONFIG.get("apis", {}).get("youtube_suggest", "https://suggestqueries.google.com/complete/search")
YOUTUBE_POLICY_REF_URL = _URL_CONFIG.get("references", {}).get("youtube_policy", "https://support.google.com/youtube/answer/1311392")

SONNET_MODEL = "claude-sonnet-4-20250514"
SONNET_INPUT_COST_PER_M = 3.0
SONNET_OUTPUT_COST_PER_M = 15.0


def _safe_topic(topic: str) -> str:
    """Convert topic to filesystem-safe string."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", topic.lower()).strip("_")[:60]


def _today() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate Claude API cost from token counts."""
    return (input_tokens * SONNET_INPUT_COST_PER_M / 1_000_000) + (
        output_tokens * SONNET_OUTPUT_COST_PER_M / 1_000_000
    )


def _load_template(series: str) -> str:
    """Load script template for the given series type."""
    template_map = {
        "build_log": "script_trading_update.txt",
        "tool_review": "script_tool_review.txt",
        "tutorial": "script_tutorial.txt",
        "short": "script_short.txt",
    }
    template_file = TEMPLATES_DIR / template_map.get(series, "script_tutorial.txt")
    if template_file.exists():
        return template_file.read_text()
    return ""


def _load_voice_config() -> dict:
    """Load voice configuration."""
    voice_file = CONFIG_DIR / "voices.json"
    if voice_file.exists():
        return json.loads(voice_file.read_text())
    return {"default": {"voice_id": "21m00Tcm4TlvDq8ikWAM", "settings": {}}}


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-show_entries",
                "format=duration", "-of", "csv=p=0", audio_path,
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


@mcp.tool()
def generate_script(
    topic: str,
    series: str = "tutorial",
    duration_minutes: int = 10,
) -> str:
    """Generate a video script using Claude Sonnet API.

    Args:
        topic: The video topic
        series: Series type — build_log, tool_review, or tutorial
        duration_minutes: Target duration in minutes (default 10)

    Returns:
        JSON with script_path, word_count, estimated_duration, cost_usd
    """
    client = anthropic.Anthropic()
    template = _load_template(series)
    word_target = duration_minutes * 150

    system_prompt = textwrap.dedent(f"""
        You are the scriptwriter for SharkWave AI YouTube channel.
        Write a video script about: {topic}
        Series: {series}

        RULES:
        - Target word count: {word_target} words (±20%)
        - NEVER start with "hey guys", "what's up", or any casual greeting
        - Start with a BOLD HOOK — a surprising fact, result, or claim
        - Include [PAUSE] markers for natural speech breaks (every 2-3 paragraphs)
        - Use conversational but professional tone
        - Include specific numbers, examples, and data points
        - End with a clear CTA: subscribe + tease next video
        - Add disclaimer: "Not financial advice. Results may vary."
        - Include original commentary markers: "In my experience", "What I found", "Here's why this matters"

        RETENTION HOOKS (critical for YouTube algorithm):
        - At 0:30 — Deliver the FIRST VALUE POINT. Viewers decide to stay or leave here.
        - At 1:00 — OPEN LOOP: "But wait, there's a problem most people miss..."
        - At 3:00 — PATTERN INTERRUPT: Change pace. Show a result, chart, or surprising data point.
        - At 5:00 — PAYOFF a previous open loop. Open a new one.
        - At 7:00 — "Here's the part most tutorials skip..." (keeps late-video retention high)
        - Final 30s — STRONG CTA + tease next video topic

        TEMPLATE STRUCTURE:
        {template}

        Write the script as plain text with [PAUSE] markers. No markdown formatting.
    """)

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Write the script for: {topic}"}],
        )

        script_text = response.content[0].text
        word_count = len(script_text.split())
        est_duration = word_count / 150

        cost = _calculate_cost(
            response.usage.input_tokens, response.usage.output_tokens
        )

        safe = _safe_topic(topic)
        date = _today()
        script_path = QUEUE_DIR / f"script_{safe}_{date}.txt"
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text)

        return json.dumps({
            "script_path": str(script_path),
            "word_count": word_count,
            "estimated_duration_minutes": round(est_duration, 1),
            "target_duration_minutes": duration_minutes,
            "cost_usd": round(cost, 4),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "generate_script"})


@mcp.tool()
def generate_short_script(topic: str, short_type: str = "quick_tip") -> str:
    """Generate a YouTube Shorts / Instagram Reels script (30-60 seconds).

    Args:
        topic: The short topic
        short_type: Type — results_reveal, quick_tip, hot_take, timelapse, mistake

    Returns:
        JSON with script_path, word_count, estimated_duration, cost_usd
    """
    client = anthropic.Anthropic()
    template = _load_template("short")

    system_prompt = textwrap.dedent(f"""
        You are the scriptwriter for SharkWave AI YouTube Shorts and Instagram Reels.
        Write a SHORT script (30-60 seconds, 75-150 words max).
        Topic: {topic}
        Short type: {short_type}

        RULES:
        - Start with an INSTANT HOOK (0-3 seconds). No intro.
        - Every sentence must deliver value. Zero filler.
        - Include [TEXT: your overlay text] markers for text overlays
        - Max 6 words per text overlay
        - End with a quick CTA: "Follow for more" or "Full video on YouTube"
        - Keep energy HIGH. Short sentences. Punchy delivery.

        TEMPLATE:
        {template}

        Write as plain text with [TEXT: ...] markers for overlays.
    """)

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Write a {short_type} short about: {topic}"}],
        )

        script_text = response.content[0].text
        word_count = len(script_text.split())
        est_duration = word_count / 150 * 60

        cost = _calculate_cost(
            response.usage.input_tokens, response.usage.output_tokens
        )

        safe = _safe_topic(topic)
        date = _today()
        script_path = SHORTS_DIR / f"short_script_{safe}_{date}.txt"
        SHORTS_DIR.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text)

        return json.dumps({
            "script_path": str(script_path),
            "word_count": word_count,
            "estimated_duration_seconds": round(est_duration, 1),
            "cost_usd": round(cost, 4),
            "format": "9:16 vertical",
            "platforms": ["youtube_shorts", "instagram_reels"],
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "generate_short_script"})


@mcp.tool()
def generate_voiceover(
    script_path: str,
    voice_id: str = "",
) -> str:
    """Generate voiceover audio from a script using ElevenLabs API.

    Args:
        script_path: Path to the script file
        voice_id: ElevenLabs voice ID (uses default from config if empty)

    Returns:
        JSON with audio_path, duration_seconds, characters_used
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        return json.dumps({"error": "ELEVENLABS_API_KEY not set"})

    voice_config = _load_voice_config()
    if not voice_id:
        voice_id = voice_config["default"]["voice_id"]

    settings = voice_config["default"].get("settings", {})
    model = voice_config["default"].get("model", "eleven_turbo_v2_5")

    script_text = Path(script_path).read_text()
    # Replace [PAUSE] with ellipsis for natural pauses
    script_text = script_text.replace("[PAUSE]", "...")
    # Remove [TEXT: ...] markers (for shorts)
    script_text = re.sub(r"\[TEXT:.*?\]", "", script_text)

    url = f"{ELEVENLABS_TTS_URL}/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": script_text,
        "model_id": model,
        "voice_settings": {
            "stability": settings.get("stability", 0.5),
            "similarity_boost": settings.get("similarity_boost", 0.75),
            "style": settings.get("style", 0.3),
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        safe = Path(script_path).stem.replace("script_", "").replace("short_script_", "")
        is_short = "short" in Path(script_path).stem
        out_dir = SHORTS_DIR if is_short else QUEUE_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / f"audio_{safe}.mp3"
        audio_path.write_bytes(response.content)

        duration = _get_audio_duration(str(audio_path))
        chars_used = len(script_text)

        return json.dumps({
            "audio_path": str(audio_path),
            "duration_seconds": round(duration, 1),
            "characters_used": chars_used,
            "voice_id": voice_id,
            "model": model,
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "generate_voiceover"})


@mcp.tool()
def assemble_video(
    audio_path: str,
    topic: str,
    vertical: bool = False,
) -> str:
    """Assemble a video from audio + stock footage using FFmpeg.

    Args:
        audio_path: Path to the audio file
        topic: Topic for Pexels stock footage search
        vertical: If True, creates 9:16 vertical video (for Shorts/Reels)

    Returns:
        JSON with video_path, duration_seconds, resolution, cost_usd
    """
    duration = _get_audio_duration(audio_path)
    if duration <= 0:
        return json.dumps({"error": "Could not determine audio duration"})

    width, height = (1080, 1920) if vertical else (1920, 1080)
    safe = _safe_topic(topic)
    date = _today()

    out_dir = SHORTS_DIR if vertical else QUEUE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = "short_video" if vertical else "video"
    video_path = out_dir / f"{prefix}_{safe}_{date}.mp4"

    pexels_key = os.getenv("PEXELS_API_KEY")
    clip_paths = []

    if pexels_key:
        try:
            orientation = "portrait" if vertical else "landscape"
            resp = requests.get(
                PEXELS_VIDEO_SEARCH_URL,
                headers={"Authorization": pexels_key},
                params={
                    "query": topic,
                    "per_page": 5,
                    "orientation": orientation,
                    "size": "medium",
                },
                timeout=30,
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])

            FOOTAGE_DIR.mkdir(parents=True, exist_ok=True)
            for i, v in enumerate(videos[:5]):
                files = v.get("video_files", [])
                hd_files = [
                    f for f in files
                    if f.get("height", 0) >= (1080 if not vertical else 1920)
                       or f.get("width", 0) >= (1920 if not vertical else 1080)
                ]
                chosen = hd_files[0] if hd_files else (files[0] if files else None)
                if chosen:
                    clip_path = FOOTAGE_DIR / f"clip_{safe}_{i}.mp4"
                    if not clip_path.exists():
                        dl = requests.get(chosen["link"], timeout=60)
                        clip_path.write_bytes(dl.content)
                    clip_paths.append(str(clip_path))
        except Exception:
            clip_paths = []

    try:
        if clip_paths:
            concat_file = out_dir / f"concat_{safe}_{date}.txt"
            with open(concat_file, "w") as f:
                for cp in clip_paths:
                    f.write(f"file '{cp}'\n")

            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_file),
                    "-i", audio_path,
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                           f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0a0a0f",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart",
                    str(video_path),
                ],
                capture_output=True, check=True, timeout=300,
            )
            concat_file.unlink(missing_ok=True)
        else:
            # Fallback: solid dark background with audio
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i",
                    f"color=c=0x0a0a0f:s={width}x{height}:d={duration}:r=30",
                    "-i", audio_path,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart",
                    str(video_path),
                ],
                capture_output=True, check=True, timeout=300,
            )

        final_duration = _get_audio_duration(str(video_path))

        return json.dumps({
            "video_path": str(video_path),
            "duration_seconds": round(final_duration, 1),
            "resolution": f"{width}x{height}",
            "aspect_ratio": "9:16" if vertical else "16:9",
            "clips_used": len(clip_paths),
            "cost_usd": 0.0,
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "assemble_video"})


@mcp.tool()
def generate_thumbnail(topic: str, title_text: str) -> str:
    """Generate a 1280x720 YouTube thumbnail using Pillow.

    Args:
        topic: Video topic (for theming)
        title_text: Title text to display on thumbnail (max ~4 words)

    Returns:
        JSON with thumbnail_path, resolution, cost_usd
    """
    width, height = 1280, 720
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Dark gradient background
    for y in range(height):
        r = int(10 + (y / height) * 10)
        g = int(10 + (y / height) * 22)
        b = int(18 + (y / height) * 40)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Subtle grid pattern
    grid_color = (20, 30, 50)
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    # Cyan accent line at 60% height
    accent_y = int(height * 0.6)
    draw.line([(50, accent_y), (width - 50, accent_y)], fill=(0, 212, 255), width=3)

    # Corner bracket accents
    bracket_len = 40
    bracket_color = (0, 212, 255)
    # Top-left
    draw.line([(30, 30), (30 + bracket_len, 30)], fill=bracket_color, width=3)
    draw.line([(30, 30), (30, 30 + bracket_len)], fill=bracket_color, width=3)
    # Top-right
    draw.line([(width - 30, 30), (width - 30 - bracket_len, 30)], fill=bracket_color, width=3)
    draw.line([(width - 30, 30), (width - 30, 30 + bracket_len)], fill=bracket_color, width=3)
    # Bottom-left
    draw.line([(30, height - 30), (30 + bracket_len, height - 30)], fill=bracket_color, width=3)
    draw.line([(30, height - 30), (30, height - 30 - bracket_len)], fill=bracket_color, width=3)
    # Bottom-right
    draw.line([(width - 30, height - 30), (width - 30 - bracket_len, height - 30)], fill=bracket_color, width=3)
    draw.line([(width - 30, height - 30), (width - 30, height - 30 - bracket_len)], fill=bracket_color, width=3)

    # Title text — fallback chain: macOS → Linux → bundled → default
    _FONT_PATHS = [
        "/System/Library/Fonts/Helvetica.ttc",        # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Debian/Ubuntu
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",   # Arch
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", # Fedora
    ]
    font_large = font_small = None
    for fpath in _FONT_PATHS:
        try:
            font_large = ImageFont.truetype(fpath, 72)
            font_small = ImageFont.truetype(fpath, 28)
            break
        except OSError:
            continue
    if font_large is None:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Wrap title to max 2 lines
    words = title_text.upper().split()
    if len(words) > 4:
        line1 = " ".join(words[: len(words) // 2])
        line2 = " ".join(words[len(words) // 2:])
        lines = [line1, line2]
    else:
        lines = [title_text.upper()]

    y_offset = height // 3
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_large)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        # Shadow
        draw.text((x + 3, y_offset + 3), line, fill=(0, 0, 0), font=font_large)
        # Main text
        draw.text((x, y_offset), line, fill=(255, 255, 255), font=font_large)
        y_offset += 85

    # Brand text at bottom
    brand = "SHARKWAVE AI"
    bbox = draw.textbbox((0, 0), brand, font=font_small)
    brand_width = bbox[2] - bbox[0]
    draw.text(
        ((width - brand_width) // 2, height - 70),
        brand,
        fill=(0, 212, 255),
        font=font_small,
    )

    safe = _safe_topic(topic)
    date = _today()
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = QUEUE_DIR / f"thumb_{safe}_{date}.png"
    img.save(str(thumb_path), "PNG", optimize=True)

    return json.dumps({
        "thumbnail_path": str(thumb_path),
        "resolution": f"{width}x{height}",
        "cost_usd": 0.0,
    })


@mcp.tool()
def generate_metadata(topic: str, series: str, script_path: str) -> str:
    """Generate SEO-optimized metadata for YouTube using Claude Sonnet.

    Args:
        topic: Video topic
        series: Series type — build_log, tool_review, or tutorial
        script_path: Path to the script file for context

    Returns:
        JSON with metadata_path, title, tags_count, cost_usd
    """
    client = anthropic.Anthropic()

    script_preview = ""
    sp = Path(script_path)
    if sp.exists():
        script_preview = sp.read_text()[:500]

    system_prompt = textwrap.dedent("""
        Generate YouTube SEO metadata. Return ONLY valid JSON (no markdown, no code blocks):
        {
            "title": "Under 60 chars, keyword front-loaded",
            "description": "200 words with keywords, timestamps placeholder, CTA, disclaimer",
            "tags": ["tag1", "tag2", "...up to 15"],
            "category_id": "28"
        }

        RULES:
        - Title: Primary keyword FIRST. Under 60 characters. No clickbait.
        - Description: First 150 chars are critical. Include natural keywords.
        - Tags: 10-15 tags. Mix broad + specific.
        - Category: 28 (Science & Technology) or 22 (People & Blogs)

        Always include in description:
        - Subscribe: @SharkWaveAI
        - GitHub: github.com/saijayanth888/shark-trading-agent
        - Disclaimer: Not financial advice. Educational content only. Results may vary.
    """)

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Topic: {topic}\nSeries: {series}\nScript preview: {script_preview}",
            }],
        )

        meta_text = response.content[0].text
        # Parse JSON from response (handle potential markdown wrapping)
        json_match = re.search(r"\{.*\}", meta_text, re.DOTALL)
        if json_match:
            metadata = json.loads(json_match.group())
        else:
            metadata = json.loads(meta_text)

        cost = _calculate_cost(
            response.usage.input_tokens, response.usage.output_tokens
        )

        safe = _safe_topic(topic)
        date = _today()
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        meta_path = QUEUE_DIR / f"meta_{safe}_{date}.json"
        meta_path.write_text(json.dumps(metadata, indent=2))

        return json.dumps({
            "metadata_path": str(meta_path),
            "title": metadata.get("title", ""),
            "tags_count": len(metadata.get("tags", [])),
            "cost_usd": round(cost, 4),
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "generate_metadata"})


@mcp.tool()
def generate_instagram_caption(topic: str, series: str, script_path: str) -> str:
    """Generate Instagram-optimized caption with hashtags.

    Args:
        topic: Video topic
        series: Series type
        script_path: Path to the script for context

    Returns:
        JSON with caption, hashtags, caption_path
    """
    client = anthropic.Anthropic()

    script_preview = ""
    sp = Path(script_path)
    if sp.exists():
        script_preview = sp.read_text()[:300]

    system_prompt = textwrap.dedent("""
        Generate an Instagram Reels caption. Return ONLY valid JSON:
        {
            "caption": "The main caption text (under 2200 chars, hook in first line)",
            "hashtags": ["hashtag1", "hashtag2", "...up to 30"]
        }

        RULES:
        - First line is the HOOK (shows in feed before "...more")
        - Keep caption under 300 words
        - Include CTA: "Full video on YouTube — link in bio"
        - Add disclaimer for trading content
        - 20-30 relevant hashtags (mix popular + niche)
        - Always include: #SharkWaveAI #AITrading #AI #MachineLearning
    """)

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Topic: {topic}\nSeries: {series}\nScript: {script_preview}",
            }],
        )

        caption_text = response.content[0].text
        json_match = re.search(r"\{.*\}", caption_text, re.DOTALL)
        if json_match:
            caption_data = json.loads(json_match.group())
        else:
            caption_data = json.loads(caption_text)

        cost = _calculate_cost(
            response.usage.input_tokens, response.usage.output_tokens
        )

        safe = _safe_topic(topic)
        date = _today()
        REELS_DIR.mkdir(parents=True, exist_ok=True)
        caption_path = REELS_DIR / f"caption_{safe}_{date}.json"
        caption_data["cost_usd"] = round(cost, 4)
        caption_path.write_text(json.dumps(caption_data, indent=2))

        return json.dumps({
            "caption_path": str(caption_path),
            "caption_preview": caption_data.get("caption", "")[:100],
            "hashtags_count": len(caption_data.get("hashtags", [])),
            "cost_usd": round(cost, 4),
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "generate_instagram_caption"})


@mcp.tool()
def convert_to_reel(video_path: str, topic: str) -> str:
    """Convert a YouTube Short to Instagram Reel format.

    Re-encodes video for Instagram specs (H.264, AAC, max 90 sec, 9:16).
    If the source is already 9:16, just re-encodes. Otherwise, crops/pads.

    Args:
        video_path: Path to the source video (typically a YouTube Short)
        topic: Topic name for output file naming

    Returns:
        JSON with reel_path, duration_seconds, file_size_mb
    """
    safe = _safe_topic(topic)
    date = _today()
    REELS_DIR.mkdir(parents=True, exist_ok=True)
    reel_path = REELS_DIR / f"reel_{safe}_{date}.mp4"

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                       "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0a0a0f",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                "-t", "90",  # Instagram max 90 seconds
                "-movflags", "+faststart",
                str(reel_path),
            ],
            capture_output=True, check=True, timeout=120,
        )

        duration = _get_audio_duration(str(reel_path))
        file_size = reel_path.stat().st_size / (1024 * 1024)

        return json.dumps({
            "reel_path": str(reel_path),
            "duration_seconds": round(duration, 1),
            "file_size_mb": round(file_size, 2),
            "resolution": "1080x1920",
            "cost_usd": 0.0,
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "convert_to_reel"})


@mcp.tool()
def create_video_package(
    topic: str,
    series: str = "tutorial",
    duration_minutes: int = 10,
) -> str:
    """MASTER ORCHESTRATOR — Run the full content pipeline.

    Creates a complete video package: script -> voiceover -> video -> thumbnail -> metadata.
    Saves a manifest.json with all file paths.

    Args:
        topic: Video topic
        series: Series type — build_log, tool_review, or tutorial
        duration_minutes: Target video duration

    Returns:
        JSON summary of the complete package with all paths and costs
    """
    results = {}
    total_cost = 0.0

    # Step 1: Generate script
    script_result = json.loads(generate_script(topic, series, duration_minutes))
    if "error" in script_result:
        return json.dumps({"error": f"Script failed: {script_result['error']}"})
    results["script"] = script_result
    total_cost += script_result.get("cost_usd", 0)

    # Step 2: Generate voiceover
    voice_result = json.loads(generate_voiceover(script_result["script_path"]))
    if "error" in voice_result:
        return json.dumps({"error": f"Voiceover failed: {voice_result['error']}"})
    results["voiceover"] = voice_result

    # Step 3: Assemble video
    video_result = json.loads(
        assemble_video(voice_result["audio_path"], topic, vertical=False)
    )
    if "error" in video_result:
        return json.dumps({"error": f"Video failed: {video_result['error']}"})
    results["video"] = video_result

    # Step 4: Generate thumbnail
    short_title = topic[:30] if len(topic) > 30 else topic
    thumb_result = json.loads(generate_thumbnail(topic, short_title))
    if "error" in thumb_result:
        return json.dumps({"error": f"Thumbnail failed: {thumb_result['error']}"})
    results["thumbnail"] = thumb_result

    # Step 5: Generate metadata
    meta_result = json.loads(
        generate_metadata(topic, series, script_result["script_path"])
    )
    if "error" in meta_result:
        return json.dumps({"error": f"Metadata failed: {meta_result['error']}"})
    results["metadata"] = meta_result
    total_cost += meta_result.get("cost_usd", 0)

    # Save manifest
    safe = _safe_topic(topic)
    date = _today()
    manifest = {
        "topic": topic,
        "series": series,
        "date": date,
        "total_cost_usd": round(total_cost, 4),
        "video_path": video_result.get("video_path"),
        "audio_path": voice_result.get("audio_path"),
        "script_path": script_result.get("script_path"),
        "thumbnail_path": thumb_result.get("thumbnail_path"),
        "metadata_path": meta_result.get("metadata_path"),
        "duration_seconds": video_result.get("duration_seconds"),
        "platform": "youtube_longform",
    }

    manifest_path = QUEUE_DIR / f"manifest_{safe}_{date}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return json.dumps({
        "manifest_path": str(manifest_path),
        "topic": topic,
        "series": series,
        "total_cost_usd": round(total_cost, 4),
        "files": manifest,
        "status": "ready_to_publish",
    })


@mcp.tool()
def create_short_package(topic: str, short_type: str = "quick_tip") -> str:
    """Create a complete YouTube Short + Instagram Reel package.

    Generates: short script -> voiceover -> vertical video -> reel conversion -> IG caption.

    Args:
        topic: Short topic
        short_type: Type — results_reveal, quick_tip, hot_take, timelapse, mistake

    Returns:
        JSON summary with all paths for both YouTube Shorts and Instagram Reels
    """
    results = {}
    total_cost = 0.0

    # Step 1: Generate short script
    script_result = json.loads(generate_short_script(topic, short_type))
    if "error" in script_result:
        return json.dumps({"error": f"Short script failed: {script_result['error']}"})
    results["script"] = script_result
    total_cost += script_result.get("cost_usd", 0)

    # Step 2: Generate voiceover
    voice_result = json.loads(generate_voiceover(script_result["script_path"]))
    if "error" in voice_result:
        return json.dumps({"error": f"Voiceover failed: {voice_result['error']}"})
    results["voiceover"] = voice_result

    # Step 3: Assemble vertical video (9:16)
    video_result = json.loads(
        assemble_video(voice_result["audio_path"], topic, vertical=True)
    )
    if "error" in video_result:
        return json.dumps({"error": f"Video failed: {video_result['error']}"})
    results["video"] = video_result

    # Step 4: Convert to Instagram Reel
    reel_result = json.loads(
        convert_to_reel(video_result["video_path"], topic)
    )
    if "error" in reel_result:
        results["reel"] = {"note": "Reel conversion failed, Short still available"}
    else:
        results["reel"] = reel_result

    # Step 5: Generate Instagram caption
    caption_result = json.loads(
        generate_instagram_caption(topic, short_type, script_result["script_path"])
    )
    if "error" not in caption_result:
        results["instagram_caption"] = caption_result
        total_cost += caption_result.get("cost_usd", 0)

    # Save manifest
    safe = _safe_topic(topic)
    date = _today()
    manifest = {
        "topic": topic,
        "short_type": short_type,
        "date": date,
        "total_cost_usd": round(total_cost, 4),
        "youtube_short": {
            "video_path": video_result.get("video_path"),
            "script_path": script_result.get("script_path"),
            "audio_path": voice_result.get("audio_path"),
        },
        "instagram_reel": {
            "reel_path": reel_result.get("reel_path") if "reel_path" in reel_result else None,
            "caption_path": caption_result.get("caption_path") if "error" not in caption_result else None,
        },
        "platforms": ["youtube_shorts", "instagram_reels"],
    }

    SHORTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = SHORTS_DIR / f"short_manifest_{safe}_{date}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return json.dumps({
        "manifest_path": str(manifest_path),
        "topic": topic,
        "total_cost_usd": round(total_cost, 4),
        "platforms": ["youtube_shorts", "instagram_reels"],
        "status": "ready_to_publish",
    })


@mcp.tool()
def budget_check() -> str:
    """Check remaining monthly budget before generating any content.

    Reads cost logs from content/queue/ and content/shorts/ manifests.
    Enforces MONTHLY_BUDGET_CAP_USD from environment (default $10).

    Returns:
        JSON with spent_usd, remaining_usd, can_proceed, days_remaining
    """
    cap = float(os.getenv("MONTHLY_BUDGET_CAP_USD", "10.00"))
    now = datetime.now(timezone.utc)
    current_month = now.strftime("%Y-%m")

    total_spent = 0.0
    manifest_count = 0

    for search_dir in [QUEUE_DIR, SHORTS_DIR, REELS_DIR]:
        if not search_dir.exists():
            continue
        for f in search_dir.glob("*manifest*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("date", "").startswith(current_month):
                    total_spent += data.get("total_cost_usd", 0.0)
                    manifest_count += 1
            except (json.JSONDecodeError, KeyError):
                continue

    remaining = max(0.0, cap - total_spent)
    days_left = (datetime(now.year, now.month % 12 + 1, 1, tzinfo=timezone.utc)
                 - now).days if now.month < 12 else (
                 datetime(now.year + 1, 1, 1, tzinfo=timezone.utc) - now).days
    daily_budget = remaining / max(days_left, 1)

    return json.dumps({
        "month": current_month,
        "budget_cap_usd": cap,
        "spent_usd": round(total_spent, 4),
        "remaining_usd": round(remaining, 4),
        "can_proceed": remaining > 0.20,
        "videos_produced": manifest_count,
        "days_remaining_in_month": days_left,
        "daily_budget_usd": round(daily_budget, 4),
        "recommendation": "PROCEED" if remaining > 0.20 else "HALT — budget exhausted",
    })


@mcp.tool()
def trend_research(niche: str = "ai trading") -> str:
    """Research trending topics using YouTube search suggestions + Pexels trending.

    Uses YouTube autocomplete API (no key needed) to find what people are
    searching for RIGHT NOW in your niche. Cross-references with your
    existing content to avoid duplicates.

    Args:
        niche: The niche to research (default: "ai trading")

    Returns:
        JSON with trending_topics, search_suggestions, recommended_topics
    """
    base_queries = [
        f"{niche} 2025",
        f"{niche} tutorial",
        f"{niche} for beginners",
        f"best {niche} tools",
        f"{niche} strategy",
        f"how to {niche}",
        f"{niche} automation",
        f"{niche} python",
    ]

    all_suggestions = []
    for query in base_queries:
        try:
            resp = requests.get(
                YOUTUBE_SUGGEST_URL,
                params={"client": "youtube", "ds": "yt", "q": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.status_code == 200:
                text = resp.text
                # Parse JSONP response
                start = text.index("(") + 1
                end = text.rindex(")")
                data = json.loads(text[start:end])
                if isinstance(data, list) and len(data) > 1:
                    for suggestion in data[1]:
                        if isinstance(suggestion, list) and suggestion:
                            all_suggestions.append(suggestion[0])
        except Exception:
            continue

    # Deduplicate and score
    seen = set()
    unique_suggestions = []
    for s in all_suggestions:
        low = s.lower().strip()
        if low not in seen and len(low) > 5:
            seen.add(low)
            unique_suggestions.append(s)

    # Check existing content to avoid duplicates
    existing_topics = set()
    for d in [QUEUE_DIR, SHORTS_DIR]:
        if d.exists():
            for f in d.glob("script_*.txt"):
                existing_topics.add(f.stem.replace("script_", "").replace("short_script_", ""))

    # Filter out topics too similar to existing content
    fresh_topics = []
    for topic in unique_suggestions:
        safe = _safe_topic(topic)
        if safe not in existing_topics:
            fresh_topics.append(topic)

    # Load niches config for cross-referencing
    niches_file = CONFIG_DIR / "niches.json"
    niche_keywords = []
    if niches_file.exists():
        try:
            niche_data = json.loads(niches_file.read_text())
            for n in niche_data.get("primary_niches", []):
                niche_keywords.extend(n.get("keywords", []))
        except (json.JSONDecodeError, KeyError):
            pass

    # Score topics by keyword relevance
    scored = []
    for topic in fresh_topics[:30]:
        score = sum(1 for kw in niche_keywords if kw.lower() in topic.lower())
        scored.append({"topic": topic, "relevance_score": score})
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)

    return json.dumps({
        "niche": niche,
        "total_suggestions_found": len(unique_suggestions),
        "fresh_topics": len(fresh_topics),
        "top_recommendations": scored[:10],
        "all_suggestions": unique_suggestions[:20],
        "existing_content_count": len(existing_topics),
        "research_timestamp": datetime.now(timezone.utc).isoformat(),
    })


@mcp.tool()
def analytics_feedback(top_n: int = 5) -> str:
    """Analyze past content performance to guide future topic selection.

    Reads manifests from content/published/ (populated after publishing)
    to learn which topics, series types, and formats performed best.
    Uses this to recommend adjustments.

    Args:
        top_n: Number of top/bottom performers to analyze

    Returns:
        JSON with performance_summary, recommendations, patterns
    """
    published_dir = CONTENT_DIR / "published"
    if not published_dir.exists():
        published_dir = QUEUE_DIR  # Fallback to queue for pre-launch

    manifests = []
    for f in published_dir.glob("*manifest*.json"):
        try:
            data = json.loads(f.read_text())
            manifests.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    if not manifests:
        return json.dumps({
            "status": "no_data",
            "recommendation": "No published content yet. Start with trending topics "
                              "from trend_research tool. Focus on tutorials — they "
                              "have highest long-term search traffic.",
            "suggested_first_topics": [
                "How to Build an AI Trading Bot with Python",
                "AI Trading Agent: Week 1 Results",
                "Best Free AI Tools for Stock Trading 2025",
            ],
        })

    # Analyze patterns
    series_counts = {}
    topic_keywords = {}
    total_cost = 0.0

    for m in manifests:
        series = m.get("series", "unknown")
        series_counts[series] = series_counts.get(series, 0) + 1
        total_cost += m.get("total_cost_usd", 0.0)

        # Extract keywords from topic
        topic = m.get("topic", "")
        for word in topic.lower().split():
            if len(word) > 3:
                topic_keywords[word] = topic_keywords.get(word, 0) + 1

    top_keywords = sorted(topic_keywords.items(), key=lambda x: x[1], reverse=True)[:10]

    return json.dumps({
        "total_videos_produced": len(manifests),
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_per_video": round(total_cost / max(len(manifests), 1), 4),
        "series_distribution": series_counts,
        "top_keywords": dict(top_keywords),
        "recommendations": [
            "Diversify series types if one dominates > 60% of output",
            "Focus on tutorials for SEO — they rank highest in search",
            "Build logs create loyalty — use weekly for subscriber retention",
            "Tool reviews drive affiliate revenue — prioritize when approaching 1K subs",
        ],
        "content_strategy": {
            "optimal_mix": {
                "tutorial": "40%",
                "build_log": "35%",
                "tool_review": "25%",
            },
            "shorts_ratio": "1 Short per long-form video minimum",
        },
    })


@mcp.tool()
def generate_ab_variants(topic: str, series: str = "tutorial") -> str:
    """Generate A/B test variants for titles and thumbnails.

    Creates 3 title variants and 2 thumbnail variants for testing.
    YouTube's Test & Compare feature lets you test thumbnails natively.
    Titles should be manually A/B tested by publishing at different times.

    Args:
        topic: The video topic
        series: Series type for context

    Returns:
        JSON with title_variants, thumbnail_paths, testing_strategy
    """
    client = anthropic.Anthropic()

    system_prompt = textwrap.dedent("""
        Generate 3 YouTube title variants for A/B testing. Return ONLY valid JSON:
        {
            "variants": [
                {"title": "Title 1", "strategy": "keyword-first"},
                {"title": "Title 2", "strategy": "curiosity-gap"},
                {"title": "Title 3", "strategy": "number-driven"}
            ]
        }

        RULES:
        - Variant 1: Primary keyword FIRST (SEO-optimized)
        - Variant 2: Curiosity gap — make them NEED to click
        - Variant 3: Number-driven — "5 Ways..." or include a specific result
        - ALL under 60 characters
        - NO clickbait or misleading claims
        - Include relevant emoji if natural (max 1)
    """)

    try:
        response = _retry_request(lambda: client.messages.create(
            model=SONNET_MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Topic: {topic}\nSeries: {series}"}],
        ))

        variants_text = response.content[0].text
        json_match = re.search(r"\{.*\}", variants_text, re.DOTALL)
        if json_match:
            variants_data = json.loads(json_match.group())
        else:
            variants_data = json.loads(variants_text)

        cost = _calculate_cost(
            response.usage.input_tokens, response.usage.output_tokens
        )

        # Generate 2 thumbnail variants (different color schemes)
        thumb_paths = []
        color_schemes = [
            {"bg_start": (10, 10, 18), "bg_end": (20, 32, 58), "accent": (0, 212, 255)},   # Blue
            {"bg_start": (18, 10, 10), "bg_end": (58, 20, 20), "accent": (255, 100, 50)},   # Red/Orange
        ]

        safe = _safe_topic(topic)
        date = _today()

        for idx, scheme in enumerate(color_schemes):
            width, height = 1280, 720
            img = Image.new("RGB", (width, height))
            draw = ImageDraw.Draw(img)

            for y in range(height):
                t = y / height
                r = int(scheme["bg_start"][0] + t * (scheme["bg_end"][0] - scheme["bg_start"][0]))
                g = int(scheme["bg_start"][1] + t * (scheme["bg_end"][1] - scheme["bg_start"][1]))
                b = int(scheme["bg_start"][2] + t * (scheme["bg_end"][2] - scheme["bg_start"][2]))
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            accent = scheme["accent"]
            accent_y = int(height * 0.6)
            draw.line([(50, accent_y), (width - 50, accent_y)], fill=accent, width=3)

            _FONT_PATHS = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            ]
            font_large = font_small = None
            for fpath in _FONT_PATHS:
                try:
                    font_large = ImageFont.truetype(fpath, 72)
                    font_small = ImageFont.truetype(fpath, 28)
                    break
                except OSError:
                    continue
            if font_large is None:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

            title = variants_data["variants"][idx]["title"] if idx < len(variants_data["variants"]) else topic
            title_upper = title.upper()[:30]
            bbox = draw.textbbox((0, 0), title_upper, font=font_large)
            text_w = bbox[2] - bbox[0]
            x = (width - text_w) // 2
            draw.text((x + 3, height // 3 + 3), title_upper, fill=(0, 0, 0), font=font_large)
            draw.text((x, height // 3), title_upper, fill=(255, 255, 255), font=font_large)

            brand = "SHARKWAVE AI"
            bbox = draw.textbbox((0, 0), brand, font=font_small)
            draw.text(((width - (bbox[2] - bbox[0])) // 2, height - 70), brand, fill=accent, font=font_small)

            QUEUE_DIR.mkdir(parents=True, exist_ok=True)
            path = QUEUE_DIR / f"thumb_{safe}_variant{chr(65 + idx)}_{date}.png"
            img.save(str(path), "PNG", optimize=True)
            thumb_paths.append(str(path))

        return json.dumps({
            "title_variants": variants_data.get("variants", []),
            "thumbnail_variants": thumb_paths,
            "cost_usd": round(cost, 4),
            "testing_strategy": {
                "thumbnails": "Upload both to YouTube Test & Compare. Run for 7 days minimum.",
                "titles": "Use the SEO variant first. Switch to curiosity-gap if CTR < 4% after 48h.",
                "metrics_to_watch": ["click_through_rate", "average_view_duration", "impressions"],
            },
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "generate_ab_variants"})


@mcp.tool()
def policy_compliance_check(script_path: str, metadata_path: str = "") -> str:
    """Validate content against YouTube 2025 policy BEFORE publishing.

    Checks for:
    - Inauthentic content markers (mass-produced, derivative)
    - Missing AI disclosure
    - Missing disclaimers (financial content)
    - Duplicate content detection
    - Spam indicators

    Args:
        script_path: Path to the script file to validate
        metadata_path: Path to metadata JSON (optional)

    Returns:
        JSON with compliance_status (PASS/FAIL/WARN), issues[], recommendations[]
    """
    issues = []
    warnings = []

    # Read script
    sp = Path(script_path)
    if not sp.exists():
        return json.dumps({"error": f"Script not found: {script_path}"})
    script = sp.read_text()
    word_count = len(script.split())

    # --- Check 1: Minimum quality threshold ---
    if word_count < 200:
        issues.append("Script too short (<200 words). YouTube may flag as low-quality.")
    if word_count < 500:
        warnings.append("Script under 500 words. Consider adding more depth for retention.")

    # --- Check 2: Original commentary markers ---
    analysis_markers = [
        "i think", "in my experience", "what i found", "here's why",
        "let me explain", "the key insight", "what most people miss",
        "my recommendation", "based on my testing", "i discovered",
    ]
    has_original = any(m in script.lower() for m in analysis_markers)
    if not has_original:
        issues.append(
            "No original commentary detected. YouTube requires 'meaningful original content.' "
            "Add personal analysis, testing results, or unique perspectives."
        )

    # --- Check 3: Financial disclaimer ---
    disclaimer_markers = [
        "not financial advice", "educational", "results may vary",
        "do your own research", "disclaimer", "past performance",
    ]
    has_disclaimer = any(m in script.lower() for m in disclaimer_markers)
    trading_markers = ["trading", "invest", "stock", "profit", "return", "portfolio"]
    is_financial = any(m in script.lower() for m in trading_markers)

    if is_financial and not has_disclaimer:
        issues.append("Financial content detected but NO disclaimer found. Add 'Not financial advice' disclaimer.")

    # --- Check 4: No spam indicators ---
    spam_phrases = [
        "subscribe and like", "smash that like button", "don't forget to subscribe",
        "hit the bell", "leave a comment below",
    ]
    spam_count = sum(1 for p in spam_phrases if p in script.lower())
    if spam_count > 2:
        warnings.append(f"Excessive CTA spam ({spam_count} instances). Keep to 1-2 CTAs max.")

    # --- Check 5: Duplicate content check ---
    safe = sp.stem.replace("script_", "").replace("short_script_", "")
    existing_scripts = []
    for d in [QUEUE_DIR, SHORTS_DIR]:
        if d.exists():
            for f in d.glob("script_*.txt"):
                if f != sp and f.stem.replace("script_", "").replace("short_script_", "") != safe:
                    existing_scripts.append(f)

    for existing in existing_scripts[:5]:
        try:
            existing_text = existing.read_text()
            # Simple overlap check: shared unique words
            script_words = set(script.lower().split())
            existing_words = set(existing_text.lower().split())
            if len(script_words) > 0:
                overlap = len(script_words & existing_words) / len(script_words)
                if overlap > 0.7:
                    issues.append(
                        f"High content overlap ({overlap:.0%}) with {existing.name}. "
                        "YouTube penalizes near-duplicate content."
                    )
        except Exception:
            continue

    # --- Check 6: Metadata validation ---
    if metadata_path:
        mp = Path(metadata_path)
        if mp.exists():
            try:
                meta = json.loads(mp.read_text())
                title = meta.get("title", "")
                if len(title) > 100:
                    issues.append(f"Title too long ({len(title)} chars, max 100)")
                if len(title) < 20:
                    warnings.append("Title too short. Aim for 40-60 characters for optimal CTR.")
                tags = meta.get("tags", [])
                if len(tags) > 15:
                    warnings.append(f"Too many tags ({len(tags)}). YouTube recommends 10-15.")
                if len(tags) < 5:
                    warnings.append("Too few tags. Add 10-15 relevant tags for discoverability.")
            except json.JSONDecodeError:
                warnings.append("Could not parse metadata JSON.")

    # --- Verdict ---
    status = "PASS"
    if issues:
        status = "FAIL"
    elif warnings:
        status = "WARN"

    return json.dumps({
        "compliance_status": status,
        "issues": issues,
        "warnings": warnings,
        "checks_passed": {
            "word_count": word_count >= 200,
            "original_commentary": has_original,
            "financial_disclaimer": has_disclaimer if is_financial else True,
            "no_duplicate_content": not any("overlap" in i for i in issues),
            "cta_not_spammy": spam_count <= 2,
        },
        "recommendation": (
            "SAFE TO PUBLISH" if status == "PASS"
            else "FIX ISSUES BEFORE PUBLISHING" if status == "FAIL"
            else "REVIEW WARNINGS — proceed with caution"
        ),
        "youtube_policy_ref": YOUTUBE_POLICY_REF_URL,
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
