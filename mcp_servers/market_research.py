"""
Shark Content Factory — Market Research MCP Server

FastMCP server providing tools for:
- YouTube trending topic research
- Competitor channel analysis (public data only)
- Content gap analysis
- Analytics-driven feedback loop
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# --- Production config ---
_ENV = os.getenv("ENVIRONMENT", "development")


def mask_error_details(error: Exception) -> str:
    if _ENV == "production":
        return f"Internal error in market_research [{type(error).__name__}]"
    return str(error)


mcp = FastMCP(
    "market-research",
    **({"log_level": "WARNING"} if _ENV == "production" else {}),
)

CONTENT_DIR = Path(__file__).parent.parent / "content"
CONFIG_DIR = Path(__file__).parent.parent / "config"
QUEUE_DIR = CONTENT_DIR / "queue"
SHORTS_DIR = CONTENT_DIR / "shorts"

# --- Centralized URL config ---
_URLS_PATH = CONFIG_DIR / "urls.json"
_URL_CONFIG = json.loads(_URLS_PATH.read_text()) if _URLS_PATH.exists() else {}
YOUTUBE_SUGGEST_URL = _URL_CONFIG.get("apis", {}).get(
    "youtube_suggest", "https://suggestqueries.google.com/complete/search"
)


def _safe_topic(topic: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9\s]", "", topic).strip().lower().replace(" ", "_")
    return safe[:60]


@mcp.tool()
def trend_research(niche: str = "ai trading") -> str:
    """Research trending topics using YouTube search suggestions.

    Uses YouTube autocomplete API (no key needed) to find what people
    are searching for RIGHT NOW. Cross-references with existing content
    and niche keywords for relevance scoring.

    Args:
        niche: The niche to research (default: ai trading)

    Returns:
        JSON with trending_topics, search_suggestions, recommendations
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
                start = text.index("(") + 1
                end = text.rindex(")")
                data = json.loads(text[start:end])
                if isinstance(data, list) and len(data) > 1:
                    for suggestion in data[1]:
                        if isinstance(suggestion, list) and suggestion:
                            all_suggestions.append(suggestion[0])
        except Exception:
            continue

    seen = set()
    unique_suggestions = []
    for s in all_suggestions:
        low = s.lower().strip()
        if low not in seen and len(low) > 5:
            seen.add(low)
            unique_suggestions.append(s)

    existing_topics = set()
    for d in [QUEUE_DIR, SHORTS_DIR]:
        if d.exists():
            for f in d.glob("script_*.txt"):
                existing_topics.add(
                    f.stem.replace("script_", "").replace("short_script_", "")
                )

    fresh_topics = []
    for topic in unique_suggestions:
        safe = _safe_topic(topic)
        if safe not in existing_topics:
            fresh_topics.append(topic)

    niches_file = CONFIG_DIR / "niches.json"
    niche_keywords = []
    if niches_file.exists():
        try:
            niche_data = json.loads(niches_file.read_text())
            for n in niche_data.get("primary_niches", []):
                niche_keywords.extend(n.get("keywords", []))
        except (json.JSONDecodeError, KeyError):
            pass

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
def competitor_analysis(channel_ids: list[str] | None = None) -> str:
    """Analyze competitor YouTube channels using public data.

    Uses YouTube Data API to pull public metrics. Only accesses
    publicly available data (no scraping, no TOS violations).

    Args:
        channel_ids: YouTube channel IDs to analyze.
                     Falls back to channels in config/niches.json.

    Returns:
        JSON with competitor metrics and recent video titles
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    try:
        token_path = os.path.expanduser(
            os.getenv(
                "YOUTUBE_TOKEN_PATH",
                "~/.shark-content-factory/youtube_token.json",
            )
        )
        if not os.path.exists(token_path):
            return json.dumps({
                "error": "OAuth token required for competitor analysis",
                "fallback": "Use trend_research for topic ideas without API access",
            })

        creds = Credentials.from_authorized_user_file(token_path)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        youtube = build("youtube", "v3", credentials=creds)

        if not channel_ids:
            niches_file = CONFIG_DIR / "niches.json"
            if niches_file.exists():
                niche_data = json.loads(niches_file.read_text())
                channel_ids = []
                for n in niche_data.get("primary_niches", []):
                    for url in n.get("competitors", []):
                        handle = url.rstrip("/").split("@")[-1] if "@" in url else ""
                        if handle:
                            search = youtube.search().list(
                                part="snippet",
                                q=handle,
                                type="channel",
                                maxResults=1,
                            ).execute()
                            if search.get("items"):
                                channel_ids.append(
                                    search["items"][0]["snippet"]["channelId"]
                                )

        if not channel_ids:
            return json.dumps({
                "status": "no_competitors",
                "recommendation": "Add competitor channel URLs to config/niches.json",
            })

        competitors = []
        for cid in channel_ids[:5]:
            try:
                ch = youtube.channels().list(
                    part="snippet,statistics",
                    id=cid,
                ).execute()

                if ch.get("items"):
                    item = ch["items"][0]
                    stats = item.get("statistics", {})
                    comp = {
                        "channel_id": cid,
                        "name": item["snippet"]["title"],
                        "subscribers": int(stats.get("subscriberCount", 0)),
                        "total_views": int(stats.get("viewCount", 0)),
                        "video_count": int(stats.get("videoCount", 0)),
                    }

                    recent = youtube.search().list(
                        part="snippet",
                        channelId=cid,
                        order="date",
                        maxResults=5,
                        type="video",
                    ).execute()
                    comp["recent_titles"] = [
                        v["snippet"]["title"] for v in recent.get("items", [])
                    ]
                    competitors.append(comp)
            except Exception:
                continue

        return json.dumps({
            "competitors_analyzed": len(competitors),
            "data": competitors,
            "research_timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "competitor_analysis"})


@mcp.tool()
def content_gap_analysis(niche: str = "ai trading") -> str:
    """Identify content gaps by comparing trending topics with existing content.

    Cross-references YouTube search suggestions with your existing videos
    to find untapped opportunities.

    Args:
        niche: Niche to analyze

    Returns:
        JSON with gap_opportunities ranked by potential
    """
    trend_result = json.loads(trend_research(niche))
    trending = [t["topic"] for t in trend_result.get("top_recommendations", [])]

    existing = set()
    for d in [QUEUE_DIR, SHORTS_DIR, CONTENT_DIR / "published"]:
        if d.exists():
            for f in d.glob("*manifest*.json"):
                try:
                    data = json.loads(f.read_text())
                    existing.add(data.get("topic", "").lower())
                except Exception:
                    continue

    gaps = []
    for topic in trending:
        is_covered = any(
            _safe_topic(topic) == _safe_topic(ex)
            or topic.lower() in ex
            or ex in topic.lower()
            for ex in existing
        )
        if not is_covered:
            gaps.append({
                "topic": topic,
                "status": "UNCOVERED",
                "opportunity": "HIGH" if len(topic.split()) >= 3 else "MEDIUM",
                "suggested_series": _suggest_series(topic),
                "suggested_format": (
                    "short" if len(topic.split()) <= 5 else "long_form"
                ),
            })

    return json.dumps({
        "niche": niche,
        "gaps_found": len(gaps),
        "opportunities": gaps[:15],
        "existing_content_count": len(existing),
        "recommendation": (
            f"Found {len(gaps)} untapped topics. "
            "Prioritize HIGH opportunity topics for next week's calendar."
        ),
    })


@mcp.tool()
def analytics_feedback(top_n: int = 5) -> str:
    """Analyze past content performance to guide future topic selection.

    Reads manifests from content directories to identify patterns
    in what performs best. Provides data-driven recommendations.

    Args:
        top_n: Number of top/bottom performers to analyze

    Returns:
        JSON with performance_summary, recommendations, patterns
    """
    published_dir = CONTENT_DIR / "published"
    if not published_dir.exists():
        published_dir = QUEUE_DIR

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
            "recommendation": (
                "No published content yet. Start with trending topics "
                "from trend_research tool. Focus on tutorials — they "
                "have highest long-term search traffic."
            ),
            "suggested_first_topics": [
                "How to Build an AI Trading Bot with Python",
                "AI Trading Agent: Week 1 Results",
                "Best Free AI Tools for Stock Trading 2025",
            ],
        })

    series_counts = {}
    topic_keywords = {}
    total_cost = 0.0

    for m in manifests:
        series = m.get("series", "unknown")
        series_counts[series] = series_counts.get(series, 0) + 1
        total_cost += m.get("total_cost_usd", 0.0)

        topic = m.get("topic", "")
        for word in topic.lower().split():
            if len(word) > 3:
                topic_keywords[word] = topic_keywords.get(word, 0) + 1

    top_keywords = sorted(
        topic_keywords.items(), key=lambda x: x[1], reverse=True
    )[:10]

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
            "Tool reviews drive affiliate revenue — prioritize near 1K subs",
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


def _suggest_series(topic: str) -> str:
    """Suggest the best series type for a topic."""
    topic_lower = topic.lower()
    if any(w in topic_lower for w in ["review", "compare", "vs", "best", "tool"]):
        return "tool_review"
    elif any(w in topic_lower for w in ["build", "log", "week", "results", "update"]):
        return "build_log"
    return "tutorial"


if __name__ == "__main__":
    mcp.run(transport="stdio")
