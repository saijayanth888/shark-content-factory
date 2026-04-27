# Market Research Agent Routine — Deep Market Intelligence

> **Schedule:** Bi-weekly, 1st and 15th at 9 AM ET (`0 9 1,15 * *`)
> **Agent Role:** Market Research Agent — Competitor & niche analysis
> **MCP Servers:** `market-research`, `sheets-api`

## Objective

Perform deep market intelligence gathering every two weeks. Analyze competitor
channels, identify niche gaps, and write findings to Google Sheets for the
Research Agent to consume during weekly planning.

## Workflow

### Step 1: Competitor Analysis

Call `competitor_analysis` from `market-research`:

```
competitor_analysis()
```

This pulls public metrics from competitor channels defined in `config/niches.json`.
Note recent video titles, subscriber counts, and upload frequency.

### Step 2: Content Gap Analysis

Call `content_gap_analysis` from `market-research` for each primary niche:

```
content_gap_analysis(niche="ai trading")
content_gap_analysis(niche="algorithmic trading python")
content_gap_analysis(niche="ai finance tools")
```

Collect HIGH opportunity gaps.

### Step 3: Trend Research (Broad)

Call `trend_research` from `market-research` with broader queries to catch
emerging trends outside the core niche:

```
trend_research(niche="ai tools 2025")
trend_research(niche="python automation finance")
trend_research(niche="machine learning trading")
```

### Step 4: Write Competitor Intelligence to Sheets

For each competitor analyzed, call `write_market_intelligence` from `sheets-api`:

```
write_market_intelligence(
    research_type="competitor_analysis",
    data_points=[
        {
            "competitor": "<channel_name>",
            "data_point": "Subs: <count>, Videos: <count>, Recent: <titles>",
            "score": "<subscriber_count>",
            "recommendation": "<what to learn from them>"
        }
    ],
    agent="market_research_agent"
)
```

### Step 5: Write Gap Opportunities to Sheets

```
write_market_intelligence(
    research_type="content_gap",
    data_points=[
        {
            "data_point": "<gap topic>",
            "score": "<opportunity_level>",
            "recommendation": "<suggested series and format>"
        }
    ],
    agent="market_research_agent"
)
```

### Step 6: Write Trend Intelligence to Sheets

```
write_market_intelligence(
    research_type="trend",
    data_points=[
        {
            "data_point": "<trending topic>",
            "score": "<relevance_score>",
            "recommendation": "<urgency: cover this week / next week / backlog>"
        }
    ],
    agent="market_research_agent"
)
```

### Step 7: Audit Trail

Call `log_audit_event` from `sheets-api`:

```
log_audit_event(
    agent="market_research_agent",
    action="BI_WEEKLY_RESEARCH",
    details="Analyzed N competitors, found M content gaps, N trending topics"
)
```

## Intelligence Categories

| Category | Purpose | Frequency |
| --- | --- | --- |
| Competitor Analysis | Track rival channels | Bi-weekly |
| Content Gaps | Find untapped topics | Bi-weekly |
| Trending Topics | Catch viral waves | Bi-weekly (deep) + weekly (light) |
| Keyword Opportunities | SEO-driven topic ideas | Bi-weekly |

## Output

- Market Intelligence tab populated with latest research
- Audit Log entry with bi-weekly summary
- Data available for Research Agent's Sunday planning session
