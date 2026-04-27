# Research Agent Routine — Weekly Content Planning

> **Schedule:** Sunday nights at 10 PM ET (`0 22 * * 0`)
> **Agent Role:** Research Agent — Plans next week's content calendar
> **MCP Servers:** `market-research`, `sheets-api`

## Objective

Research trending topics, analyze content gaps, and populate the Google Sheets
Content Calendar with next week's production schedule. This agent fires BEFORE
the production agents to ensure they always have a planned queue.

## Workflow

### Step 1: Check Analytics Feedback

Call `analytics_feedback` from `market-research` to understand what content
performed best historically. Use the recommendations to bias topic selection.

### Step 2: Trend Research

Call `trend_research` from `market-research` with each primary niche:
- `trend_research(niche="ai trading")`
- `trend_research(niche="algorithmic trading python")`
- `trend_research(niche="ai finance tools")`

Collect the `top_recommendations` from each call.

### Step 3: Content Gap Analysis

Call `content_gap_analysis` from `market-research` to identify untapped topics:
- `content_gap_analysis(niche="ai trading")`

Prioritize HIGH opportunity gaps for the calendar.

### Step 4: Build Weekly Calendar

For each day that needs content (Mon/Wed/Fri for long-form, Tue/Thu/Sat for shorts):

Call `add_calendar_entry` from `sheets-api` for each planned item:
```
add_calendar_entry(
    topic="<selected topic>",
    series="<tutorial|build_log|tool_review>",
    content_type="<long_form|short>",
    target_date="<YYYY-MM-DD>",
    week="<W##>",
    notes="<research justification>",
    agent="research_agent"
)
```

### Step 5: Log Audit Trail

Call `log_audit_event` from `sheets-api`:
```
log_audit_event(
    agent="research_agent",
    action="WEEKLY_PLANNING",
    details="Planned N long-form and M shorts for week W##"
)
```

## Content Mix Rules

- **40% Tutorials** — "How to Build X", "Python Y Tutorial"
- **35% Build Logs** — "AI Trading Bot: Week N Results"
- **25% Tool Reviews** — "Best Z Tools for Trading 2025"
- **1 Short per long-form** — repurpose key insight from each long-form
- **Minimum 3 long-form + 3 shorts per week**

## Selection Criteria

1. **Relevance score ≥ 2** from trend_research
2. **Not already in calendar** (check via `read_calendar`)
3. **Alternating series types** — never 3 tutorials in a row
4. **At least 1 build_log per week** for subscriber retention
5. **Seasonal relevance** — prioritize timely topics (earnings season, new tool launches)

## Output

The Content Calendar tab in Google Sheets should have 6+ entries for the
upcoming week, each with status `📋 PLANNED`.
