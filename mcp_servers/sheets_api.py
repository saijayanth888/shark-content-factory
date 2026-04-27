"""
Shark Content Factory — Google Sheets State Machine MCP Server

FastMCP server providing tools for:
- Content calendar management (state machine)
- Cost tracking and budget monitoring
- Audit logging for all agent actions
- Performance metrics storage
- Asset provenance registry
- Market intelligence data

This is the coordination backbone — all agents read from and write to Sheets.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

# --- Production config ---
_ENV = os.getenv("ENVIRONMENT", "development")


def mask_error_details(error: Exception) -> str:
    if _ENV == "production":
        return f"Internal error in sheets_api [{type(error).__name__}]"
    return str(error)


mcp = FastMCP(
    "sheets-api",
    **({"log_level": "WARNING"} if _ENV == "production" else {}),
)

# --- Tab definitions ---
TAB_CALENDAR = "Content Calendar"
TAB_COSTS = "Cost Tracker"
TAB_PERFORMANCE = "Performance Metrics"
TAB_AUDIT = "Audit Log"
TAB_ASSETS = "Asset Registry"
TAB_MARKET = "Market Intelligence"

CALENDAR_HEADERS = [
    "Week", "Date", "Topic", "Series", "Type", "Status",
    "Script Path", "Video Path", "Thumbnail Path", "Cost USD",
    "Agent", "Notes", "Created At", "Updated At",
]

COST_HEADERS = [
    "Date", "Topic", "Series", "Script Cost", "Voice Cost",
    "Video Cost", "Total Cost", "Monthly Running", "Budget Cap",
    "Budget Remaining", "Agent",
]

PERFORMANCE_HEADERS = [
    "Video ID", "Title", "Published Date", "Views", "Impressions",
    "CTR %", "Avg View Duration", "Avg View %", "Likes", "Comments",
    "Shares", "Subs Gained", "Subs Lost", "Est Revenue", "CPM",
    "Composite Score", "Updated At",
]

AUDIT_HEADERS = [
    "Timestamp", "Agent", "Action", "Details", "Status Change",
    "Duration Sec", "Error",
]

ASSET_HEADERS = [
    "Video ID", "Asset Type", "Source", "Source ID", "License",
    "Voice ID", "Model Version", "AI Disclosure", "Copyright Status",
    "Created At",
]

MARKET_HEADERS = [
    "Date", "Research Type", "Competitor", "Data Point", "Score",
    "Recommendation", "Agent",
]

ALL_TABS = {
    TAB_CALENDAR: CALENDAR_HEADERS,
    TAB_COSTS: COST_HEADERS,
    TAB_PERFORMANCE: PERFORMANCE_HEADERS,
    TAB_AUDIT: AUDIT_HEADERS,
    TAB_ASSETS: ASSET_HEADERS,
    TAB_MARKET: MARKET_HEADERS,
}


# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------

def _get_sheets_service():
    """Build and return Google Sheets API service."""
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
    return build("sheets", "v4", credentials=creds)


def _get_spreadsheet_id() -> str:
    """Get the configured spreadsheet ID."""
    sid = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    if not sid:
        raise ValueError(
            "GOOGLE_SHEETS_SPREADSHEET_ID not set. "
            "Create a Google Sheet and add the ID to .env"
        )
    return sid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_audit(service, spreadsheet_id, agent, action, details,
               status_change="", duration_sec=0.0, error=""):
    """Internal helper to append an audit log row."""
    row = [
        _now_iso(), agent, action, details,
        status_change, str(duration_sec) if duration_sec else "",
        error,
    ]
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{TAB_AUDIT}'!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def init_spreadsheet() -> str:
    """Initialize the Shark Content Factory spreadsheet with all 6 tabs.

    Creates tabs if they don't exist and sets up headers.
    Safe to call multiple times — won't overwrite existing data.

    Returns:
        JSON with spreadsheet_id, tabs_created, status
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
        ).execute()
        existing_tabs = {
            s["properties"]["title"]
            for s in sheet_metadata.get("sheets", [])
        }

        tabs_created = []

        for tab_name, headers in ALL_TABS.items():
            if tab_name not in existing_tabs:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "requests": [{
                            "addSheet": {
                                "properties": {"title": tab_name}
                            }
                        }]
                    },
                ).execute()
                tabs_created.append(tab_name)

            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A1:Z1",
            ).execute()

            if not result.get("values"):
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{tab_name}'!A1",
                    valueInputOption="RAW",
                    body={"values": [headers]},
                ).execute()

        return json.dumps({
            "spreadsheet_id": spreadsheet_id,
            "tabs_created": tabs_created,
            "tabs_verified": list(ALL_TABS.keys()),
            "status": "initialized",
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "init_spreadsheet"})


@mcp.tool()
def add_calendar_entry(
    topic: str,
    series: str,
    content_type: str,
    target_date: str,
    week: str = "",
    notes: str = "",
    agent: str = "research_agent",
) -> str:
    """Add a content item to the Content Calendar.

    Args:
        topic: Video topic
        series: Series type (tutorial, build_log, tool_review)
        content_type: long_form or short
        target_date: Target publish date (YYYY-MM-DD)
        week: Week identifier (e.g. W18)
        notes: Research notes or justification
        agent: Which agent created this entry

    Returns:
        JSON with status
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        now = _now_iso()
        row = [
            week, target_date, topic, series, content_type,
            "📋 PLANNED", "", "", "", "",
            agent, notes, now, now,
        ]

        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_CALENDAR}'!A:N",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        _log_audit(service, spreadsheet_id, agent, "ADD_CALENDAR",
                   f"Added: {topic} ({series}) for {target_date}", "→ 📋 PLANNED")

        return json.dumps({
            "topic": topic,
            "target_date": target_date,
            "status": "📋 PLANNED",
            "agent": agent,
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "add_calendar_entry"})


@mcp.tool()
def update_content_status(
    topic: str,
    date: str,
    new_status: str,
    agent: str,
    notes: str = "",
    script_path: str = "",
    video_path: str = "",
    thumbnail_path: str = "",
    cost_usd: float = 0.0,
) -> str:
    """Update the status of a content item in the Calendar (state machine).

    Valid statuses (in order):
        📋 PLANNED → 🔨 PRODUCED → ⚖️ IN REVIEW →
        ✅ APPROVED → 🚀 PUBLISHED
        (or ❌ REJECTED / ⏸ HOLD at any stage)

    Args:
        topic: Video topic to find
        date: Target date of the content item (YYYY-MM-DD)
        new_status: New status value
        agent: Which agent is making the update
        notes: Additional notes
        script_path: Path to script (if produced)
        video_path: Path to video (if produced)
        thumbnail_path: Path to thumbnail (if produced)
        cost_usd: Production cost (if applicable)

    Returns:
        JSON with previous_status, new_status, row_updated
    """
    valid_statuses = [
        "📋 PLANNED", "🔨 PRODUCED", "⚖️ IN REVIEW",
        "✅ APPROVED", "❌ REJECTED", "⏸ HOLD", "🚀 PUBLISHED",
    ]
    if new_status not in valid_statuses:
        return json.dumps({"error": f"Invalid status: {new_status}. Valid: {valid_statuses}"})

    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_CALENDAR}'!A:N",
        ).execute()
        rows = result.get("values", [])

        target_row = None
        previous_status = ""
        for i, row in enumerate(rows[1:], start=2):
            row_date = row[1] if len(row) > 1 else ""
            row_topic = row[2] if len(row) > 2 else ""
            if row_date == date and topic.lower() in row_topic.lower():
                target_row = i
                previous_status = row[5] if len(row) > 5 else ""
                break

        if not target_row:
            return json.dumps({"error": f"Content not found: {topic} on {date}"})

        updates = {f"'{TAB_CALENDAR}'!F{target_row}": [[new_status]]}
        updates[f"'{TAB_CALENDAR}'!N{target_row}"] = [[_now_iso()]]

        if notes:
            existing_notes = rows[target_row - 1][11] if len(rows[target_row - 1]) > 11 else ""
            combined = f"{existing_notes} | {agent}: {notes}" if existing_notes else f"{agent}: {notes}"
            updates[f"'{TAB_CALENDAR}'!L{target_row}"] = [[combined]]
        if script_path:
            updates[f"'{TAB_CALENDAR}'!G{target_row}"] = [[script_path]]
        if video_path:
            updates[f"'{TAB_CALENDAR}'!H{target_row}"] = [[video_path]]
        if thumbnail_path:
            updates[f"'{TAB_CALENDAR}'!I{target_row}"] = [[thumbnail_path]]
        if cost_usd > 0:
            updates[f"'{TAB_CALENDAR}'!J{target_row}"] = [[str(round(cost_usd, 4))]]

        for range_name, values in updates.items():
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                body={"values": values},
            ).execute()

        _log_audit(service, spreadsheet_id, agent, "STATUS_UPDATE",
                   f"{topic}: {previous_status} → {new_status}",
                   f"{previous_status} → {new_status}")

        return json.dumps({
            "topic": topic,
            "date": date,
            "previous_status": previous_status,
            "new_status": new_status,
            "row_updated": target_row,
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "update_content_status"})


@mcp.tool()
def read_calendar(
    status_filter: str = "",
    date_filter: str = "",
    week_filter: str = "",
) -> str:
    """Read content items from the Content Calendar.

    Args:
        status_filter: Only return items with this status (e.g. '📋 PLANNED')
        date_filter: Only return items for this date (YYYY-MM-DD)
        week_filter: Only return items for this week (e.g. W18)

    Returns:
        JSON with items list and count
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_CALENDAR}'!A:N",
        ).execute()
        rows = result.get("values", [])

        if len(rows) <= 1:
            return json.dumps({"items": [], "count": 0, "status": "empty_calendar"})

        headers = rows[0]
        items = []
        for row in rows[1:]:
            padded = row + [""] * (len(headers) - len(row))
            item = dict(zip(headers, padded))

            if status_filter and item.get("Status") != status_filter:
                continue
            if date_filter and item.get("Date") != date_filter:
                continue
            if week_filter and item.get("Week") != week_filter:
                continue
            items.append(item)

        return json.dumps({"items": items, "count": len(items)})

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "read_calendar"})


@mcp.tool()
def log_cost(
    date: str,
    topic: str,
    series: str,
    script_cost: float = 0.0,
    voice_cost: float = 0.0,
    video_cost: float = 0.0,
    agent: str = "production_agent",
) -> str:
    """Log production costs to the Cost Tracker tab.

    Automatically calculates monthly running total and remaining budget.

    Args:
        date: Production date (YYYY-MM-DD)
        topic: Video topic
        series: Series type
        script_cost: Claude API cost
        voice_cost: ElevenLabs cost (estimated)
        video_cost: Other video production costs
        agent: Which agent logged this

    Returns:
        JSON with total_cost, monthly_running, budget_remaining
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        total = round(script_cost + voice_cost + video_cost, 4)
        cap = float(os.getenv("MONTHLY_BUDGET_CAP_USD", "10.00"))

        current_month = date[:7]
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_COSTS}'!A:K",
        ).execute()
        rows = result.get("values", [])

        monthly_total = 0.0
        for row in rows[1:]:
            if len(row) > 0 and row[0].startswith(current_month):
                try:
                    monthly_total += float(row[6]) if len(row) > 6 else 0.0
                except ValueError:
                    continue

        monthly_running = round(monthly_total + total, 4)
        remaining = round(max(0.0, cap - monthly_running), 4)

        row = [
            date, topic, series,
            str(round(script_cost, 4)),
            str(round(voice_cost, 4)),
            str(round(video_cost, 4)),
            str(total),
            str(monthly_running),
            str(cap),
            str(remaining),
            agent,
        ]

        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_COSTS}'!A:K",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        return json.dumps({
            "date": date,
            "topic": topic,
            "total_cost": total,
            "monthly_running": monthly_running,
            "budget_cap": cap,
            "budget_remaining": remaining,
            "can_proceed": remaining > 0.20,
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "log_cost"})


@mcp.tool()
def budget_check() -> str:
    """Check remaining monthly budget from the Cost Tracker.

    Reads the Cost Tracker tab to calculate spent vs remaining budget.

    Returns:
        JSON with spent_usd, remaining_usd, can_proceed, daily_budget
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        now = datetime.now(timezone.utc)
        current_month = now.strftime("%Y-%m")
        cap = float(os.getenv("MONTHLY_BUDGET_CAP_USD", "10.00"))

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_COSTS}'!A:K",
        ).execute()
        rows = result.get("values", [])

        total_spent = 0.0
        video_count = 0
        for row in rows[1:]:
            if len(row) > 0 and row[0].startswith(current_month):
                try:
                    total_spent += float(row[6]) if len(row) > 6 else 0.0
                    video_count += 1
                except ValueError:
                    continue

        remaining = max(0.0, cap - total_spent)
        days_left = (
            datetime(now.year, now.month % 12 + 1, 1, tzinfo=timezone.utc) - now
        ).days if now.month < 12 else (
            datetime(now.year + 1, 1, 1, tzinfo=timezone.utc) - now
        ).days
        daily_budget = remaining / max(days_left, 1)

        return json.dumps({
            "month": current_month,
            "budget_cap_usd": cap,
            "spent_usd": round(total_spent, 4),
            "remaining_usd": round(remaining, 4),
            "can_proceed": remaining > 0.20,
            "videos_produced": video_count,
            "days_remaining_in_month": days_left,
            "daily_budget_usd": round(daily_budget, 4),
            "recommendation": "PROCEED" if remaining > 0.20 else "HALT — budget exhausted",
            "source": "google_sheets",
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "budget_check"})


@mcp.tool()
def log_audit_event(
    agent: str,
    action: str,
    details: str,
    status_change: str = "",
    duration_sec: float = 0.0,
    error: str = "",
) -> str:
    """Log an agent action to the Audit Log tab.

    Every agent should call this for key actions to maintain traceability.

    Args:
        agent: Agent name (research_agent, production_agent, etc.)
        action: Action performed (e.g. GENERATE_SCRIPT, UPLOAD_VIDEO)
        details: Human-readable description
        status_change: Status transition if applicable
        duration_sec: How long the action took
        error: Error message if action failed

    Returns:
        JSON with logged status
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()
        _log_audit(service, spreadsheet_id, agent, action, details,
                   status_change, duration_sec, error)
        return json.dumps({"status": "logged", "agent": agent, "action": action})

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "log_audit_event"})


@mcp.tool()
def log_asset_provenance(
    video_id: str,
    asset_type: str,
    source: str,
    source_id: str = "",
    license_type: str = "",
    voice_id: str = "",
    model_version: str = "",
    ai_disclosure: str = "required",
    copyright_status: str = "clear",
) -> str:
    """Log asset origin and licensing to the Asset Registry.

    Every asset used in a video must be registered for legal compliance.

    Args:
        video_id: YouTube video ID (or 'pending' before upload)
        asset_type: script, voiceover, footage, thumbnail, music
        source: Origin (anthropic, elevenlabs, pexels, original)
        source_id: Specific source identifier (e.g. Pexels video ID)
        license_type: CC0, Pexels License, ElevenLabs TOS, etc.
        voice_id: ElevenLabs voice ID if voiceover
        model_version: AI model used (e.g. claude-sonnet-4-20250514)
        ai_disclosure: required, not_required, disclosed
        copyright_status: clear, pending_review, flagged

    Returns:
        JSON with logged status
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        row = [
            video_id, asset_type, source, source_id, license_type,
            voice_id, model_version, ai_disclosure, copyright_status,
            _now_iso(),
        ]

        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_ASSETS}'!A:J",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        return json.dumps({
            "status": "registered",
            "video_id": video_id,
            "asset_type": asset_type,
            "source": source,
            "copyright_status": copyright_status,
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "log_asset_provenance"})


@mcp.tool()
def write_performance_metrics(
    video_id: str,
    title: str,
    published_date: str,
    views: int = 0,
    impressions: int = 0,
    ctr_percent: float = 0.0,
    avg_view_duration: str = "0:00",
    avg_view_percent: float = 0.0,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    subs_gained: int = 0,
    subs_lost: int = 0,
    est_revenue: float = 0.0,
    cpm: float = 0.0,
) -> str:
    """Write or update video performance metrics in the Performance tab.

    If a row already exists for the video_id it is updated in place.

    Args:
        video_id: YouTube video ID
        title: Video title
        published_date: Date published
        views: Total views
        impressions: Total impressions
        ctr_percent: Click-through rate %
        avg_view_duration: Average view duration (M:SS)
        avg_view_percent: Average % of video watched
        likes: Total likes
        comments: Total comments
        shares: Total shares
        subs_gained: Subscribers gained
        subs_lost: Subscribers lost
        est_revenue: Estimated revenue USD
        cpm: Cost per mille

    Returns:
        JSON with composite_score, status
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        engagement_rate = (likes + comments + shares) / max(views, 1) * 100
        composite = round(ctr_percent * avg_view_percent * engagement_rate / 100, 2)

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{TAB_PERFORMANCE}'!A:Q",
        ).execute()
        rows = result.get("values", [])

        existing_row = None
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > 0 and row[0] == video_id:
                existing_row = i
                break

        data = [
            video_id, title, published_date, str(views), str(impressions),
            str(round(ctr_percent, 2)), avg_view_duration,
            str(round(avg_view_percent, 1)), str(likes), str(comments),
            str(shares), str(subs_gained), str(subs_lost),
            str(round(est_revenue, 4)), str(round(cpm, 2)),
            str(composite), _now_iso(),
        ]

        if existing_row:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{TAB_PERFORMANCE}'!A{existing_row}:Q{existing_row}",
                valueInputOption="RAW",
                body={"values": [data]},
            ).execute()
        else:
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"'{TAB_PERFORMANCE}'!A:Q",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [data]},
            ).execute()

        return json.dumps({
            "video_id": video_id,
            "composite_score": composite,
            "status": "updated" if existing_row else "created",
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "write_performance_metrics"})


@mcp.tool()
def write_market_intelligence(
    research_type: str,
    data_points: list[dict],
    agent: str = "market_research_agent",
) -> str:
    """Write market research findings to the Market Intelligence tab.

    Args:
        research_type: competitor_analysis, keyword_opportunity, content_gap, trend
        data_points: List of dicts with keys: competitor, data_point, score, recommendation
        agent: Which agent produced this research

    Returns:
        JSON with rows_written count
    """
    try:
        service = _get_sheets_service()
        spreadsheet_id = _get_spreadsheet_id()

        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = []
        for dp in data_points:
            rows.append([
                date,
                research_type,
                dp.get("competitor", ""),
                dp.get("data_point", ""),
                str(dp.get("score", "")),
                dp.get("recommendation", ""),
                agent,
            ])

        if rows:
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"'{TAB_MARKET}'!A:G",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            ).execute()

        return json.dumps({
            "research_type": research_type,
            "rows_written": len(rows),
            "date": date,
        })

    except Exception as e:
        return json.dumps({"error": mask_error_details(e), "tool": "write_market_intelligence"})


if __name__ == "__main__":
    mcp.run(transport="stdio")
