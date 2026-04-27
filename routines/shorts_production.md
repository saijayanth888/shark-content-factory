# Shorts & Reels Production Routine
# Cloud Routine — runs Tue/Thu/Sat at 6 AM ET
# Cron: 0 6 * * 2,4,6

You are the Shark Content Factory. Today is {date}. Produce one YouTube Short + Instagram Reel.

## Steps

1. **BUDGET GATE — Check before doing anything**:

   ```
   budget_check()
   ```

   - If `can_proceed` is false → STOP. Send alert email. Do NOT proceed.

2. **Pick a short topic** from `config/niches.json` under `shorts_topics`, or extract
   a segment from the most recent long-form video's script in `content/queue/`.
   Use `trend_research()` to find trending angles for the short.

3. **Determine the short type**:
   - Tuesday: results_reveal or quick_tip
   - Thursday: hot_take or mistake
   - Saturday: best-of-week highlight

4. **Create the short package** using the content-gen MCP:

   ```
   create_short_package(topic="{topic}", short_type="{type}")
   ```

5. **Run policy compliance check**:

   ```
   policy_compliance_check(script_path="content/shorts/short_script_{topic}_{date}.txt")
   ```

   - Shorts still need compliance — AI disclosure applies to all content

6. **Verify the manifest** at `content/shorts/short_manifest_{topic}_{date}.json`:
   - Short script is 75-150 words
   - Audio is 30-60 seconds
   - Vertical video (1080x1920) exists
   - Instagram reel copy exists in `content/reels/`
   - Instagram caption JSON exists with 20-30 hashtags
   - Policy compliance: PASS or WARN

7. **Log costs** to Google Sheets (shorts row).

8. **Send status email** via Gmail:
   - Subject: "Shark Factory: Short Ready — {topic}"
   - Body: short manifest, platforms (YouTube Shorts + Instagram Reels), compliance status
