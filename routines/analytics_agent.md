# Analytics Agent Routine — Performance Capture & Feedback Loop

> **Schedule:** Monday mornings at 8 AM ET (`0 8 * * 1`)
> **Agent Role:** Analytics Agent — Captures metrics, tracks milestones
> **MCP Servers:** `youtube-api`, `sheets-api`

## Objective

Pull comprehensive analytics for all published videos, update the Performance
Metrics tab in Google Sheets, track subscriber milestones, and generate
data-driven recommendations for the Research Agent.

## Workflow

### Step 1: Check Subscriber Milestones

Call `get_subscriber_milestones` from `youtube-api`:

This returns current subscriber count, watch hours, and progress toward
YouTube Partner Program thresholds. Log the results.

### Step 2: Get Published Videos

Call `read_calendar` from `sheets-api`:

```
read_calendar(status_filter="🚀 PUBLISHED")
```

For each published video that has a Video ID, perform Step 3.

### Step 3: Pull Deep Analytics

For each video, call `get_deep_analytics` from `youtube-api`:

```
get_deep_analytics(video_id="<video_id>", days=28)
```

This returns views, impressions, CTR, retention, revenue, traffic sources.

### Step 4: Write Performance Metrics to Sheets

For each video's analytics, call `write_performance_metrics` from `sheets-api`:

```
write_performance_metrics(
    video_id="<video_id>",
    title="<title>",
    published_date="<date>",
    views=<views>,
    impressions=<impressions>,
    ctr_percent=<ctr>,
    avg_view_duration="<duration>",
    avg_view_percent=<pct>,
    likes=<likes>,
    comments=<comments>,
    shares=<shares>,
    subs_gained=<subs_gained>,
    subs_lost=<subs_lost>,
    est_revenue=<revenue>,
    cpm=<cpm>
)
```

### Step 5: Generate Performance Summary

Analyze the collected metrics to identify:

- **Top performer** — highest composite score
- **Worst performer** — lowest composite score
- **Best CTR** — which thumbnail/title combo works best
- **Best retention** — which topic keeps viewers watching
- **Revenue trends** — is CPM improving?

### Step 6: Log Milestone Progress

Call `log_audit_event` from `sheets-api`:

```
log_audit_event(
    agent="analytics_agent",
    action="WEEKLY_ANALYTICS",
    details="Subs: <count> (<+/-change>). Videos analyzed: <N>. Top: <title>. YPP progress: <pct>%"
)
```

### Step 7: Write Recommendations to Market Intelligence

Call `write_market_intelligence` from `sheets-api` with performance insights:

```
write_market_intelligence(
    research_type="performance_feedback",
    data_points=[
        {"data_point": "Top series type", "score": "<composite>", "recommendation": "<series>"},
        {"data_point": "Best posting time", "recommendation": "<day/time>"},
        {"data_point": "CTR benchmark", "score": "<avg_ctr>", "recommendation": "<action>"}
    ],
    agent="analytics_agent"
)
```

## Key Metrics to Track

| Metric | Target | Action if Below |
|--------|--------|-----------------|
| CTR | > 4% | Improve thumbnails/titles |
| Avg View Duration | > 50% | Improve hooks and pacing |
| Engagement Rate | > 5% | Add more CTAs, questions |
| Subs per Video | > 2 | Improve channel branding |
| CPM | > $5 | Target higher-CPM niches |

## Output

- Performance Metrics tab updated with latest data for all published videos
- Audit Log entry with weekly summary
- Market Intelligence entries with data-driven recommendations
