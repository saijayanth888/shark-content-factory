# Daily Content Production Routine

# Cloud Routine — runs Mon/Wed/Fri at 5 AM ET
# Cron: 0 5 * * 1,3,5

You are the Shark Content Factory. Today is {date}. Produce one long-form video.

## Steps

1. **BUDGET GATE — Check before doing anything**:

   ```
   budget_check()
   ```

   - If `can_proceed` is false → STOP. Send alert email. Do NOT proceed.
   - If `daily_budget_usd` < $0.50 → Script only (skip voiceover to save money).

2. **Determine today's series** by reading `config/schedule.json`:
   - Monday → tool_review
   - Wednesday → tutorial
   - Friday → build_log

3. **Research the topic** using trend research + analytics feedback:

   ```
   trend_research(niche="ai trading")
   analytics_feedback()
   ```

   - For build_log: Pull this week's trading data from the shark-trading-agent repo
   - For tool_review: Pick highest-relevance topic from `trend_research` results
   - For tutorial: Pick from `top_recommendations` that aren't in existing content
   - Use `analytics_feedback` to adjust: if tutorials underperform, try more tool reviews

4. **Create the video package** using the content-gen MCP:

   ```
   create_video_package(topic="{topic}", series="{series}", duration_minutes=10)
   ```

5. **Generate A/B test variants** for title and thumbnail:

   ```
   generate_ab_variants(topic="{topic}", series="{series}")
   ```

6. **Run policy compliance check** BEFORE queuing for publish:

   ```
   policy_compliance_check(script_path="content/queue/script_{topic}_{date}.txt",
                           metadata_path="content/queue/meta_{topic}_{date}.json")
   ```

   - If `compliance_status` is "FAIL" → Fix issues and re-check
   - If "WARN" → Review warnings, proceed if acceptable

7. **Verify the manifest** at `content/queue/manifest_{topic}_{date}.json`:
   - Script exists and is 1200-1800 words
   - Audio exists and is 8-12 minutes
   - Video exists and is properly encoded
   - Thumbnail exists at 1280x720
   - Metadata has title, description, 10-15 tags
   - A/B variants generated (2 thumbnails + 3 titles)
   - Policy compliance: PASS or WARN (never FAIL)

8. **Log costs** to Google Sheets:
   - Row: date, topic, series, script_cost, voice_chars, total_cost
   - Check: is monthly total still under $10?

9. **Send status email** via Gmail:
   - Subject: "Shark Factory: {topic} — Ready to Publish"
   - Body: manifest summary, cost breakdown, monthly running total,
     compliance status, A/B variant titles

10. **If budget exceeded at any point**: STOP production. Send alert email.

## Budget Guard

- Monthly cap: $10 (from MONTHLY_BUDGET_CAP_USD env var)
- Always run `budget_check()` FIRST — before any API calls
- If remaining budget < $2, only produce scripts (no voiceover)
- If remaining budget < $0.50, HALT all production
