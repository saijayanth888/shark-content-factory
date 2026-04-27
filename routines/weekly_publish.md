# Weekly Batch Publish Routine
# Cloud Routine — runs Sunday at 8 PM ET
# Cron: 0 20 * * 0

You are the Shark Content Factory. Today is Sunday {date}. Publish the week's content.

## Steps

1. **Scan the content queue** at `content/queue/` for all `manifest_*.json` files.

2. **For each manifest** (long-form videos):
   a. Load the manifest JSON
   b. Upload the video using the youtube-api MCP:
      ```
      upload_video(
          video_path=manifest.video_path,
          title=metadata.title,
          description=metadata.description,
          tags=metadata.tags,
          category_id=metadata.category_id,
          privacy="private",
          publish_at="{scheduled_datetime}"
      )
      ```
   c. Set the custom thumbnail:
      ```
      set_thumbnail(video_id="{id}", thumbnail_path=manifest.thumbnail_path)
      ```
   d. **Pin a revenue-optimized comment** (affiliate links + resources):
      ```
      pin_comment(video_id="{id}", comment_text="📌 Resources mentioned:\n- [Tool Name]: affiliate_link\n- GitHub: repo_link\n\n🦈 Full playlist: playlist_link")
      ```
   e. **Configure end screen** for subscriber growth:
      ```
      add_end_screen(video_id="{id}", subscribe_element=True, best_for_viewer=True)
      ```
   f. Add to the appropriate playlist (create if needed):
      - "Shark Agent Build Log" playlist for build_log series
      - "Build With AI" playlist for tutorial series
      - "Tool Teardowns" playlist for tool_review series

3. **Scan the shorts queue** at `content/shorts/` for all `short_manifest_*.json` files.

4. **For each short manifest**:
   a. Upload to YouTube as a Short:
      ```
      upload_video(
          video_path=manifest.youtube_short.video_path,
          title=short_title,
          is_short=True,
          privacy="private",
          publish_at="{scheduled_datetime}"
      )
      ```
   b. Queue the Instagram Reel for manual upload (or auto-publish if API is configured):
      ```
      publish_to_instagram(
          video_path=manifest.instagram_reel.reel_path,
          caption=caption_data.caption + "\n\n" + " ".join(caption_data.hashtags)
      )
      ```

5. **Schedule timing** from `config/schedule.json`:
   - Monday 10 AM ET: Tool Teardown (long-form)
   - Tuesday 12 PM ET: Short + Reel
   - Wednesday 10 AM ET: Build With AI (long-form)
   - Thursday 12 PM ET: Short + Reel
   - Friday 10 AM ET: Build Log (long-form)
   - Saturday 12 PM ET: Short + Reel

6. **Move published manifests** to `content/published/` (create dir if needed).

7. **Post a community update** to keep subscribers engaged:

   ```
   post_community_update(
       text="🦈 New videos dropping this week! Which topic are you most excited about?",
       poll_options=["AI Trading Bot Tutorial", "Tool Review", "Build Log Update", "All of the above!"]
   )
   ```

8. **Get channel analytics** and run feedback loop:

   ```
   get_channel_analytics(days=7)
   analytics_feedback()
   ```

   - Compare this week's performance to last week
   - Identify top/bottom performing content
   - Adjust next week's topic selection based on analytics

9. **Budget check** for month-end awareness:

   ```
   budget_check()
   ```

10. **Send weekly report** via Gmail:
    - Subject: "Shark Factory Weekly Report — Week of {date}"
    - Body: videos published, costs this week, total monthly cost,
      channel stats (subs, views), top performing video,
      analytics feedback recommendations, budget remaining

11. **Log to Google Sheets**: weekly summary row with publish count, costs, analytics.
