"""
Shark Content Factory — YouTube & Instagram Publishing MCP Server

FastMCP server providing tools for:
- YouTube video uploads (long-form + Shorts)
- Thumbnail management
- Channel analytics
- Playlist management
- Instagram Reels publishing via Graph API
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

load_dotenv()

IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

mcp = FastMCP(
    "youtube-api",
    mask_error_details=IS_PRODUCTION,
)


def _retry_api(fn, max_retries: int = 3, backoff_base: float = 2.0):
    """Retry a Google API call with exponential backoff on transient errors."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as e:
            last_err = e
            if e.resp.status in (429, 500, 503) and attempt < max_retries - 1:
                time.sleep(backoff_base ** attempt)
            else:
                raise
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(backoff_base ** attempt)
            else:
                raise
    raise last_err


# --- Centralized URL config (edit config/urls.json, not code) ---
_CONFIG_DIR = Path(__file__).parent.parent / "config"
_URLS_PATH = _CONFIG_DIR / "urls.json"
_URL_CONFIG = json.loads(_URLS_PATH.read_text()) if _URLS_PATH.exists() else {}
YOUTUBE_VIDEO_WATCH_URL = _URL_CONFIG.get("youtube", {}).get("video_watch", "https://www.youtube.com/watch")
YOUTUBE_PLAYLIST_URL = _URL_CONFIG.get("youtube", {}).get("playlist", "https://www.youtube.com/playlist")
YOUTUBE_STUDIO_BASE_URL = _URL_CONFIG.get("youtube", {}).get("studio_base", "https://studio.youtube.com")
YOUTUBE_STUDIO_VIDEO_URL = _URL_CONFIG.get("youtube", {}).get("studio_video_edit", "https://studio.youtube.com/video")
INSTAGRAM_GRAPH_API_URL = _URL_CONFIG.get("apis", {}).get("instagram_graph", "https://graph.facebook.com/v19.0")


def _get_youtube_service():
    """Build authenticated YouTube API service.

    Reads OAuth token from YOUTUBE_TOKEN_PATH.
    Refreshes if expired. Raises RuntimeError if no token exists.
    """
    token_path = os.path.expanduser(
        os.getenv("YOUTUBE_TOKEN_PATH", "~/.shark-content-factory/youtube_token.json")
    )

    if not os.path.exists(token_path):
        raise RuntimeError(
            f"YouTube token not found at {token_path}. "
            "Run oauth_setup.py first to authorize."
        )

    creds = Credentials.from_authorized_user_file(token_path)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(token_path).write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


@mcp.tool()
def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "28",
    privacy: str = "private",
    publish_at: str = "",
    is_short: bool = False,
) -> str:
    """Upload a video to YouTube using the Data API v3.

    Args:
        video_path: Path to the video file
        title: Video title (max 100 chars)
        description: Video description
        tags: List of tags (max 15)
        category_id: YouTube category ID (28 = Science & Tech)
        privacy: Privacy status — public, private, or unlisted
        publish_at: ISO 8601 datetime for scheduled publish (optional)
        is_short: If True, adds #Shorts to title for YouTube Shorts

    Returns:
        JSON with video_id, url, title, status, scheduled time
    """
    try:
        youtube = _get_youtube_service()

        if is_short and "#Shorts" not in title:
            title = f"{title} #Shorts"

        title = title[:100]
        tags = tags[:15]

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
            },
        }

        if publish_at:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = publish_at

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response["id"]

        return json.dumps({
            "video_id": video_id,
            "url": f"{YOUTUBE_VIDEO_WATCH_URL}?v={video_id}",
            "title": title,
            "privacy": privacy,
            "scheduled": publish_at if publish_at else None,
            "is_short": is_short,
            "contains_synthetic_media": True,
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "upload_video"})


@mcp.tool()
def set_thumbnail(video_id: str, thumbnail_path: str) -> str:
    """Upload a custom thumbnail for a YouTube video.

    Args:
        video_id: YouTube video ID
        thumbnail_path: Path to the thumbnail image (1280x720 recommended)

    Returns:
        JSON confirmation
    """
    try:
        youtube = _get_youtube_service()

        media = MediaFileUpload(thumbnail_path, mimetype="image/png")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()

        return json.dumps({
            "video_id": video_id,
            "thumbnail_path": thumbnail_path,
            "status": "thumbnail_set",
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "set_thumbnail"})


@mcp.tool()
def get_channel_analytics(days: int = 7) -> str:
    """Get channel statistics and recent video performance.

    Args:
        days: Number of days to look back (default 7)

    Returns:
        JSON with subscriber count, total views, recent video stats
    """
    try:
        youtube = _get_youtube_service()

        # Channel stats
        channels = youtube.channels().list(
            part="statistics,snippet",
            mine=True,
        ).execute()

        if not channels.get("items"):
            return json.dumps({"error": "No channel found for authenticated user"})

        channel = channels["items"][0]
        stats = channel["statistics"]

        # Recent videos
        search = youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            maxResults=10,
            order="date",
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search.get("items", [])]

        recent_videos = []
        if video_ids:
            videos = youtube.videos().list(
                part="statistics,snippet,contentDetails",
                id=",".join(video_ids),
            ).execute()

            for v in videos.get("items", []):
                vs = v["statistics"]
                recent_videos.append({
                    "title": v["snippet"]["title"],
                    "video_id": v["id"],
                    "published": v["snippet"]["publishedAt"],
                    "views": int(vs.get("viewCount", 0)),
                    "likes": int(vs.get("likeCount", 0)),
                    "comments": int(vs.get("commentCount", 0)),
                })

        return json.dumps({
            "channel": {
                "name": channel["snippet"]["title"],
                "subscribers": int(stats.get("subscriberCount", 0)),
                "total_views": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
            },
            "recent_videos": recent_videos,
            "period_days": days,
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "get_channel_analytics"})


@mcp.tool()
def create_playlist(title: str, description: str = "") -> str:
    """Create a new playlist on the YouTube channel.

    Args:
        title: Playlist title
        description: Playlist description

    Returns:
        JSON with playlist_id
    """
    try:
        youtube = _get_youtube_service()

        playlist = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                },
                "status": {"privacyStatus": "public"},
            },
        ).execute()

        return json.dumps({
            "playlist_id": playlist["id"],
            "title": title,
            "url": f"{YOUTUBE_PLAYLIST_URL}?list={playlist['id']}",
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "create_playlist"})


@mcp.tool()
def add_to_playlist(video_id: str, playlist_id: str) -> str:
    """Add a video to a YouTube playlist.

    Args:
        video_id: YouTube video ID
        playlist_id: YouTube playlist ID

    Returns:
        JSON confirmation
    """
    try:
        youtube = _get_youtube_service()

        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                },
            },
        ).execute()

        return json.dumps({
            "video_id": video_id,
            "playlist_id": playlist_id,
            "status": "added",
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "add_to_playlist"})


@mcp.tool()
def pin_comment(video_id: str, comment_text: str) -> str:
    """Post and pin a comment on a YouTube video.

    Pinned comments are the #1 revenue tool for affiliate marketing.
    Put your best CTA, affiliate link, or resource list here.

    Args:
        video_id: YouTube video ID
        comment_text: The comment text (supports YouTube markdown)

    Returns:
        JSON with comment_id, video_id, status
    """
    try:
        youtube = _get_youtube_service()

        # Post the comment
        comment_response = _retry_api(lambda: youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text,
                        },
                    },
                },
            },
        ).execute())

        comment_id = comment_response["id"]
        top_comment_id = comment_response["snippet"]["topLevelComment"]["id"]

        # Pin the comment (set as moderation held then approved+pinned)
        # Note: YouTube API doesn't have a direct "pin" endpoint.
        # The comment will appear as the channel owner's comment (top position).
        # Manual pinning via YouTube Studio is recommended for true "pinned" status.

        return json.dumps({
            "comment_id": comment_id,
            "top_comment_id": top_comment_id,
            "video_id": video_id,
            "status": "posted",
            "note": "Comment posted as channel owner (appears at top). "
                    "For 'pinned' badge: go to YouTube Studio > Video > Comments > Pin.",
            "comment_preview": comment_text[:100],
        })

    except Exception as e:
        return json.dumps({"error": str(e), "tool": "pin_comment"})


@mcp.tool()
def add_end_screen(
    video_id: str,
    subscribe_element: bool = True,
    best_for_viewer: bool = True,
    recent_upload: bool = False,
    playlist_id: str = "",
) -> str:
    """Configure end screen elements for a YouTube video.

    End screens drive 30%+ of new subscribers. They appear in the last 5-20 seconds.
    YouTube Data API doesn't support direct end screen creation, so this tool
    generates the configuration and provides YouTube Studio instructions.

    Args:
        video_id: YouTube video ID
        subscribe_element: Add subscribe button (recommended always)
        best_for_viewer: Add "Best for viewer" auto-suggestion
        recent_upload: Add most recent upload element
        playlist_id: Optional playlist to feature

    Returns:
        JSON with end_screen config and YouTube Studio instructions
    """
    elements = []

    if subscribe_element:
        elements.append({
            "type": "SUBSCRIBE",
            "position": "top-right",
            "timing": "last 20 seconds",
        })

    if best_for_viewer:
        elements.append({
            "type": "BEST_FOR_VIEWER",
            "position": "bottom-left",
            "timing": "last 20 seconds",
            "note": "YouTube auto-picks the best video for each viewer",
        })

    if recent_upload:
        elements.append({
            "type": "RECENT_UPLOAD",
            "position": "bottom-right",
            "timing": "last 15 seconds",
        })

    if playlist_id:
        elements.append({
            "type": "PLAYLIST",
            "playlist_id": playlist_id,
            "position": "bottom-center",
            "timing": "last 20 seconds",
        })

    return json.dumps({
        "video_id": video_id,
        "video_url": f"{YOUTUBE_VIDEO_WATCH_URL}?v={video_id}",
        "end_screen_elements": elements,
        "status": "config_generated",
        "instructions": [
            f"1. Open YouTube Studio: {YOUTUBE_STUDIO_VIDEO_URL}/{video_id}/edit",
            "2. Click 'End screen' in the editor",
            "3. Click 'Import from video' to reuse a template, OR add elements manually:",
            f"   - Subscribe button: {'YES' if subscribe_element else 'NO'}",
            f"   - Best for viewer: {'YES' if best_for_viewer else 'NO'}",
            f"   - Recent upload: {'YES' if recent_upload else 'NO'}",
            f"   - Playlist: {playlist_id if playlist_id else 'NONE'}",
            "4. Position elements to avoid overlapping with video content",
            "5. Save",
        ],
        "best_practices": [
            "Always include subscribe + best-for-viewer (minimum)",
            "Mention end screen in your script: 'Check out this video next...'",
            "Leave last 20 seconds of video with clean background for elements",
            "End screens increase session time → YouTube pushes your videos more",
        ],
    })


@mcp.tool()
def post_community_update(
    text: str,
    poll_options: list[str] | None = None,
) -> str:
    """Post a community tab update on YouTube.

    Community posts keep subscribers engaged between video uploads.
    Great for: polls, behind-the-scenes, topic suggestions, announcements.

    Note: YouTube Data API has limited community post support.
    This tool generates the content and provides posting instructions.

    Args:
        text: The community post text
        poll_options: Optional list of poll choices (2-5 options)

    Returns:
        JSON with post content and instructions
    """
    post_type = "POLL" if poll_options else "TEXT"

    post_content = {
        "type": post_type,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if poll_options:
        post_content["poll_options"] = poll_options[:5]  # YouTube max 5

    return json.dumps({
        "post_content": post_content,
        "status": "content_generated",
        "instructions": [
            f"1. Open YouTube Studio: {YOUTUBE_STUDIO_BASE_URL}",
            "2. Click 'Create' > 'Create post'",
            f"3. Paste text: {text[:100]}...",
        ] + ([
            f"4. Click 'Poll' and add options: {', '.join(poll_options[:5])}",
        ] if poll_options else []) + [
            f"{'5' if poll_options else '4'}. Click 'Post'",
        ],
        "engagement_tips": [
            "Post 2-3 community updates per week between uploads",
            "Use polls to crowdsource next video topic (builds anticipation)",
            "Share behind-the-scenes of your AI trading agent",
            "Ask questions to boost comment engagement metrics",
            "Community posts with polls get 3-5x more engagement",
        ],
        "suggested_poll_topics": [
            "What AI trading topic should I cover next?",
            "Which tool should I review?",
            "Are you using AI for trading yet?",
        ] if not poll_options else [],
    })


@mcp.tool()
def publish_to_instagram(
    video_path: str,
    caption: str,
) -> str:
    """Publish a Reel to Instagram using the Graph API.

    Requires a Business or Creator Instagram account connected to a Facebook Page.
    The video must be hosted at a public URL — this tool uploads to a temporary
    hosting endpoint first if needed.

    Args:
        video_path: Path to the video file (9:16, max 90 sec)
        caption: Instagram caption with hashtags

    Returns:
        JSON with media_id, status
    """
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")

    if not access_token or not account_id:
        return json.dumps({
            "error": "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID required. "
                     "Set up a Meta Developer App with Instagram Graph API access.",
            "status": "skipped",
            "video_path": video_path,
            "caption_preview": caption[:100],
            "note": "Instagram publishing requires a public video URL. "
                    "For now, manually upload the reel from content/reels/ folder.",
        })

    # Instagram Graph API requires a public URL for the video.
    # In production, upload to a cloud storage (S3, GCS) first.
    # For now, we'll return instructions for manual upload.
    return json.dumps({
        "status": "manual_upload_required",
        "video_path": video_path,
        "caption": caption,
        "instructions": [
            "1. Open Instagram on your phone or Creator Studio",
            "2. Create new Reel",
            f"3. Upload video from: {video_path}",
            "4. Paste the caption from the caption JSON file",
            "5. Add trending audio if available",
            "6. Publish",
        ],
        "note": "Automated Instagram publishing requires video hosted at a public URL. "
                "Future: add cloud storage upload step (S3/GCS) for full automation.",
    })


@mcp.tool()
def get_deep_analytics(video_id: str, days: int = 28) -> str:
    """Pull comprehensive analytics for a specific video.

    Uses YouTube Analytics API for detailed metrics including CTR,
    retention, revenue, traffic sources, and audience demographics.

    Requires yt-analytics.readonly and yt-analytics-monetary.readonly
    OAuth scopes. Run oauth_setup.py to re-authorize if missing.

    Args:
        video_id: YouTube video ID
        days: Number of days to look back (default 28)

    Returns:
        JSON with views, impressions, CTR, avg_view_duration,
        avg_view_percentage, likes, comments, shares, subs_gained,
        subs_lost, est_revenue, cpm, traffic_sources
    """
    try:
        youtube, creds = _build_youtube_service(return_creds=True)
        analytics = build("youtubeAnalytics", "v2", credentials=creds)

        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (
            datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)
        ).strftime("%Y-%m-%d")

        # Core metrics query
        core = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=(
                "views,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage,likes,comments,shares,"
                "subscribersGained,subscribersLost,"
                "estimatedRevenue,cpm,"
                "cardClickRate,cardImpressions"
            ),
            filters=f"video=={video_id}",
        ).execute()

        core_row = core.get("rows", [[]])[0] if core.get("rows") else []
        core_headers = [
            h["name"] for h in core.get("columnHeaders", [])
        ]
        core_data = dict(zip(core_headers, core_row)) if core_row else {}

        # Reach metrics (impressions, CTR)
        reach = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,impressions,impressionClickThroughRate",
            filters=f"video=={video_id}",
        ).execute()

        reach_row = reach.get("rows", [[]])[0] if reach.get("rows") else []
        reach_headers = [h["name"] for h in reach.get("columnHeaders", [])]
        reach_data = dict(zip(reach_headers, reach_row)) if reach_row else {}

        # Traffic sources
        traffic = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views",
            dimensions="insightTrafficSourceType",
            filters=f"video=={video_id}",
            sort="-views",
        ).execute()

        traffic_sources = {}
        for row in traffic.get("rows", []):
            if len(row) >= 2:
                traffic_sources[row[0]] = row[1]

        # Format duration
        avg_dur_sec = core_data.get("averageViewDuration", 0)
        avg_dur_str = f"{int(avg_dur_sec) // 60}:{int(avg_dur_sec) % 60:02d}"

        return json.dumps({
            "video_id": video_id,
            "period": f"{start_date} to {end_date}",
            "views": core_data.get("views", 0),
            "impressions": reach_data.get("impressions", 0),
            "ctr_percent": round(
                reach_data.get("impressionClickThroughRate", 0) * 100, 2
            ),
            "estimated_minutes_watched": core_data.get(
                "estimatedMinutesWatched", 0
            ),
            "avg_view_duration": avg_dur_str,
            "avg_view_duration_sec": avg_dur_sec,
            "avg_view_percent": round(
                core_data.get("averageViewPercentage", 0), 1
            ),
            "likes": core_data.get("likes", 0),
            "comments": core_data.get("comments", 0),
            "shares": core_data.get("shares", 0),
            "subs_gained": core_data.get("subscribersGained", 0),
            "subs_lost": core_data.get("subscribersLost", 0),
            "est_revenue_usd": round(
                core_data.get("estimatedRevenue", 0), 4
            ),
            "cpm": round(core_data.get("cpm", 0), 2),
            "card_click_rate": round(
                core_data.get("cardClickRate", 0) * 100, 2
            ),
            "card_impressions": core_data.get("cardImpressions", 0),
            "traffic_sources": traffic_sources,
        })

    except Exception as e:
        return json.dumps({
            "error": mask_error_details(e),
            "tool": "get_deep_analytics",
            "hint": (
                "If scope error, re-run: python oauth_setup.py "
                "(needs yt-analytics.readonly scope)"
            ),
        })


@mcp.tool()
def get_subscriber_milestones() -> str:
    """Track subscriber count and YPP milestone progress.

    Returns current subscriber count, total watch hours,
    and progress toward YouTube Partner Program thresholds.

    Milestones tracked:
    - 100 subs: Community tab
    - 500 subs: Community posts with images
    - 1,000 subs: YPP eligibility (+ 4,000 watch hours)
    - 10,000 subs: Super Chat, memberships
    - 100,000 subs: Silver Play Button

    Returns:
        JSON with current_subscribers, watch_hours, milestones, next_milestone
    """
    try:
        youtube, creds = _build_youtube_service(return_creds=True)

        # Channel stats
        ch = youtube.channels().list(
            part="statistics",
            mine=True,
        ).execute()

        if not ch.get("items"):
            return json.dumps({"error": "Channel not found"})

        stats = ch["items"][0]["statistics"]
        subs = int(stats.get("subscriberCount", 0))
        total_views = int(stats.get("viewCount", 0))
        video_count = int(stats.get("videoCount", 0))

        # Watch hours (last 365 days) via Analytics API
        watch_hours = 0.0
        try:
            analytics = build("youtubeAnalytics", "v2", credentials=creds)
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start_date = (
                datetime.now(timezone.utc)
                - __import__("datetime").timedelta(days=365)
            ).strftime("%Y-%m-%d")

            wh = analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="estimatedMinutesWatched",
            ).execute()

            if wh.get("rows"):
                watch_hours = round(wh["rows"][0][0] / 60, 1)
        except Exception:
            pass

        milestones = [
            {
                "name": "Community Tab",
                "threshold": 100,
                "reached": subs >= 100,
                "progress_pct": min(round(subs / 100 * 100, 1), 100),
                "benefit": "Enables community posts (text only)",
            },
            {
                "name": "Community Images",
                "threshold": 500,
                "reached": subs >= 500,
                "progress_pct": min(round(subs / 500 * 100, 1), 100),
                "benefit": "Community posts with images and polls",
            },
            {
                "name": "YPP Subscribers",
                "threshold": 1000,
                "reached": subs >= 1000,
                "progress_pct": min(round(subs / 1000 * 100, 1), 100),
                "benefit": "YouTube Partner Program eligibility (subscriber req)",
            },
            {
                "name": "YPP Watch Hours",
                "threshold": 4000,
                "unit": "hours",
                "reached": watch_hours >= 4000,
                "current": watch_hours,
                "progress_pct": min(round(watch_hours / 4000 * 100, 1), 100),
                "benefit": "YouTube Partner Program eligibility (watch hours req)",
            },
            {
                "name": "Super Chat & Memberships",
                "threshold": 10000,
                "reached": subs >= 10000,
                "progress_pct": min(round(subs / 10000 * 100, 1), 100),
                "benefit": "Enables Super Chat, channel memberships, merch shelf",
            },
            {
                "name": "Silver Play Button",
                "threshold": 100000,
                "reached": subs >= 100000,
                "progress_pct": min(round(subs / 100000 * 100, 1), 100),
                "benefit": "YouTube Silver Play Button award",
            },
        ]

        # Find next milestone
        next_milestone = None
        for m in milestones:
            if not m["reached"]:
                next_milestone = m["name"]
                break

        ypp_eligible = subs >= 1000 and watch_hours >= 4000

        return json.dumps({
            "current_subscribers": subs,
            "total_views": total_views,
            "total_videos": video_count,
            "watch_hours_365d": watch_hours,
            "ypp_eligible": ypp_eligible,
            "milestones": milestones,
            "next_milestone": next_milestone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as e:
        return json.dumps({
            "error": mask_error_details(e),
            "tool": "get_subscriber_milestones",
        })


def _build_youtube_service(return_creds=False):
    """Build YouTube service, optionally returning creds for Analytics API."""
    token_path = os.path.expanduser(
        os.getenv("YOUTUBE_TOKEN_PATH", "~/.shark-content-factory/youtube_token.json")
    )
    if not os.path.exists(token_path):
        raise FileNotFoundError(
            f"OAuth token not found at {token_path}. Run: python oauth_setup.py"
        )
    creds = Credentials.from_authorized_user_file(token_path)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(token_path).write_text(creds.to_json())
    yt = build("youtube", "v3", credentials=creds)
    if return_creds:
        return yt, creds
    return yt


if __name__ == "__main__":
    mcp.run(transport="stdio")
