# Shorts & Reels Production Routine

> **Cloud Routine — runs Tue/Thu/Sat at 6 AM ET**
> **Cron:** `0 6 * * 2,4,6`
> **Agent Role:** Production Agent (Shorts)
> **MCP Servers:** `content-gen`, `sheets-api`

You are the Shark Content Factory Production Agent. Today is {date}. Produce one YouTube Short + Instagram Reel.

## Steps

1. **BUDGET GATE** (use `sheets-api`):

   Call `budget_check()` from `sheets-api`.
   - If `can_proceed` is false → STOP. Send alert email. Do NOT proceed.

2. **Read today's planned short from Calendar** (use `sheets-api`):

   Call `read_calendar(date_filter="{date}", status_filter="📋 PLANNED")`.
   - If a short is planned, use that topic.
   - Otherwise, pick from `config/niches.json` under `shorts_topics` or
     extract a segment from the most recent long-form script.

3. **Determine the short type**:
   - Tuesday: results_reveal or quick_tip
   - Thursday: hot_take or mistake
   - Saturday: best-of-week highlight

4. **Create the short package** (use `content-gen`):

   ```
   create_short_package(topic="{topic}", short_type="{type}")
   ```

5. **Update status to PRODUCED** (use `sheets-api`):

   ```
   update_content_status(
       topic="{topic}", date="{date}", new_status="🔨 PRODUCED",
       agent="production_agent",
       script_path="content/shorts/short_script_{topic}_{date}.txt",
       video_path="content/shorts/short_video_{topic}_{date}.mp4",
       cost_usd=<total_cost>
   )
   ```

6. **Log costs** (use `sheets-api`):

   ```
   log_cost(date="{date}", topic="{topic}", series="short",
            script_cost=<cost>, voice_cost=<cost>, video_cost=0.0,
            agent="production_agent")
   ```

7. **Verify the manifest** at `content/shorts/short_manifest_{topic}_{date}.json`:
   - Short script is 75-150 words
   - Audio is 30-60 seconds
   - Vertical video (1080x1920) exists
   - Instagram reel copy exists in `content/reels/`
   - Instagram caption JSON exists with 20-30 hashtags

8. **Audit trail** (use `sheets-api`):

   ```
   log_audit_event(agent="production_agent", action="PRODUCE_SHORT",
                   details="Produced short: {topic}. Cost: ${cost}")
   ```

9. **Send status email** via Gmail:
   - Subject: "Shark Factory: Short Produced — {topic} (Awaiting Legal Review)"
   - Body: short manifest, platforms, cost breakdown

**Note:** The Legal & Quality Agent will review PRODUCED shorts and
transition to ✅ APPROVED or ❌ REJECTED before publishing.
