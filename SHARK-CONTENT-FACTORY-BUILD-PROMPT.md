# Shark Content Factory — Claude Code Build Prompt

> **INSTRUCTIONS:** Copy everything below the line into your Claude Code terminal in VS Code.
> Make sure you are `cd`'d into your `shark-content-factory/` repo before pasting.

---

## PASTE THIS INTO CLAUDE CODE:

```
I need you to build the Shark Content Factory — a fully automated YouTube content pipeline that researches topics, writes scripts, generates voiceovers, assembles videos, creates thumbnails, and publishes to YouTube. This is the content engine for the @SharkWaveAI YouTube channel.

## CONTEXT

- This repo is `shark-content-factory/` — it exists but is empty (README + LICENSE)
- YouTube channel: @SharkWaveAI (already created, handle confirmed)
- YouTube channel URL: https://www.youtube.com/channel/UCl8ny7zNaguOyeCCaorx8tA
- Companion repo: shark-trading-agent (the agent whose journey we document on YouTube)
- The factory runs via Claude Code Cloud Routines (cron-scheduled prompts)
- Publishing uses the official YouTube Data API v3 (NOT Playwright for YouTube UI)
- Playwright is ONLY for research — scraping trending topics, analyzing competitors
- Target: 3-5 videos/week, 8-12 minutes each, ~$1.50 per video total cost

## COST CONSTRAINTS (CRITICAL)

- Claude API: Use claude-sonnet-4-20250514 for ALL script generation (~$0.10-0.15/script)
- ElevenLabs: Starter plan at $6/mo = 30k credits = ~4 videos/month initially
- Stock footage: Pexels API (FREE)
- Video assembly: FFmpeg (FREE)
- Thumbnails: Pillow (FREE)
- YouTube uploads: YouTube Data API v3 (FREE)
- MONTHLY BUDGET CAP: $10 for content factory tools. If monthly total exceeds this, STOP and notify.

## STEP 1: CREATE THE FULL DIRECTORY STRUCTURE

```
shark-content-factory/
├── CLAUDE.md                              # Factory persona + content strategy
├── README.md                              # Project overview (update existing)
├── requirements.txt                       # Python dependencies
├── .env.template                          # Template for required env vars
├── .gitignore                             # Python + env + secrets
│
├── mcp_servers/                           # 3 MCP servers
│   ├── __init__.py
│   ├── playwright_research.py             # Trending topics + competitor analysis
│   ├── content_gen.py                     # Script + voice + video + thumbnail + metadata
│   └── youtube_api.py                     # Upload + schedule + analytics
│
├── routines/                              # Claude Code Cloud Routine prompts
│   ├── README.md                          # How to set up routines
│   ├── content-factory.md                 # Daily: research → create → queue
│   └── weekly-batch-publish.md            # Sunday: upload + schedule week
│
├── oauth_setup.py                         # Run ONCE to authorize YouTube API
│
├── content/                               # Generated content workspace
│   ├── queue/                             # Videos waiting to publish
│   │   └── .gitkeep
│   ├── published/                         # Published archive
│   │   └── .gitkeep
│   └── footage/                           # Stock footage cache
│       └── .gitkeep
│
├── templates/                             # Reusable content templates
│   ├── script_trading_update.txt          # Template for weekly Shark Agent updates
│   ├── script_tool_review.txt             # Template for AI tool reviews
│   └── script_tutorial.txt                # Template for Build With AI tutorials
│
├── config/                                # Configuration
│   ├── voices.json                        # ElevenLabs voice ID mappings
│   ├── niches.json                        # Content niches + keyword targets
│   └── schedule.json                      # Publishing schedule config
│
├── logs/                                  # Cost + publish tracking
│   ├── cost-log.csv                       # Running cost per video
│   └── publish-log.csv                    # Publication history
│
└── tests/                                 # Test suite
    ├── __init__.py
    ├── test_script_gen.py                 # Test script generation
    ├── test_metadata.py                   # Test SEO metadata
    └── test_thumbnail.py                  # Test thumbnail creation
```

## STEP 2: CREATE CLAUDE.md

```markdown
# CLAUDE.md — Shark Content Factory

## Identity
You are the Shark Content Factory — an automated YouTube content pipeline
for the @SharkWaveAI channel. You research trending topics, write scripts,
generate voiceovers, assemble videos, and publish to YouTube.

## Channel Identity
- Channel: SharkWave AI (@SharkWaveAI)
- Tagline: "AI-powered trading, automation, and smart money strategies"
- Tone: Technical but accessible. Confident but honest. Data-driven, no hype.
- Audience: Developers, traders, builders who want AI systems that make real money

## Content Strategy

### 3 Series (rotate through these)

1. **Shark Agent Build Log** (1/week)
   - Weekly update on the AI trading agent
   - What it traded, P&L results, what broke, what improved
   - Screen recordings of real trades + agent decisions
   - Always show real numbers — wins AND losses

2. **Build With AI** (1-2/week)
   - Step-by-step tutorials building real AI systems
   - "Build an AI trading bot in 48 hours"
   - "Automate X with Claude Code"
   - Always include code, always show the actual build process

3. **Tool Teardowns** (1/week)
   - Honest reviews of AI developer tools
   - Claude Code vs Cursor vs Devin vs Codex
   - MCP servers, LangGraph, Perplexity, Alpaca
   - No sponsorship bias — if a tool sucks, say so

### Video Structure (every video follows this)
1. HOOK (0-30 sec): Bold claim or surprising result. Never "hey guys what's up"
2. CONTEXT (30-60 sec): Why this matters, what viewer will learn
3. CONTENT (2-8 min): 3-5 key points with real examples
4. RESULTS (30-60 sec): Show the actual outcome / data / P&L
5. CTA (15 sec): Subscribe + next video tease

### SEO Rules
- Title: Front-load the primary keyword. Under 60 characters.
- Description: First 150 chars are critical (shown in search). Include keywords naturally.
- Tags: 10-15 tags. Mix broad ("AI trading") + specific ("Claude Code Alpaca API")
- Thumbnail: High contrast, max 4 words text, face or result screenshot

## Cost Controls
- Scripts: Claude Sonnet API only (~$0.10/script). NEVER use Opus for scripts.
- Voice: ElevenLabs turbo_v2_5 model (fastest, cheapest)
- Video: FFmpeg + free Pexels footage. NO paid video tools.
- Thumbnails: Pillow only. NO Canva subscription.
- Monthly budget cap: $10 for the factory. Track every cent in cost-log.csv.

## YouTube Compliance
- ALWAYS set containsSyntheticMedia: true on uploads (AI content disclosure)
- ALWAYS use the official YouTube Data API for uploads (never browser automation)
- Never claim guaranteed returns or financial advice
- Always add disclaimer: "Not financial advice. Results may vary."

## Publishing Schedule
- Monday 10 AM ET: Tool Teardown or Build With AI
- Wednesday 10 AM ET: Build With AI or Tool Teardown
- Friday 10 AM ET: Shark Agent Build Log (weekly P&L)

## Environment Variables
- ANTHROPIC_API_KEY
- ELEVENLABS_API_KEY
- PEXELS_API_KEY
- YOUTUBE_CLIENT_SECRETS_PATH
- YOUTUBE_TOKEN_PATH
- SENDGRID_API_KEY (optional — for publish notifications)
- NOTIFY_EMAIL (optional)
```

## STEP 3: CREATE .env.template

```
# Shark Content Factory — Environment Variables
# Copy to .env and fill in your values. NEVER commit .env to git.

# Claude API (Sonnet for scripts — cheap)
ANTHROPIC_API_KEY=your_anthropic_api_key

# ElevenLabs ($6/mo Starter plan)
ELEVENLABS_API_KEY=your_elevenlabs_api_key

# Pexels (FREE — stock footage)
PEXELS_API_KEY=your_pexels_api_key

# YouTube Data API v3 (FREE — upload + schedule)
YOUTUBE_CLIENT_SECRETS_PATH=~/.shark-content-factory/client_secrets.json
YOUTUBE_TOKEN_PATH=~/.shark-content-factory/youtube_token.json

# SendGrid (FREE tier — optional publish notifications)
SENDGRID_API_KEY=your_sendgrid_api_key
NOTIFY_EMAIL=sharkwaveai@gmail.com

# Budget guard
MONTHLY_BUDGET_CAP_USD=10.00
```

## STEP 4: CREATE .gitignore

```
.env
__pycache__/
*.pyc
.venv/
venv/
content/queue/*.mp4
content/queue/*.mp3
content/queue/*.png
content/published/
content/footage/*.mp4
*.egg-info/
dist/
build/
.pytest_cache/
.DS_Store
node_modules/
```

## STEP 5: CREATE requirements.txt

```
anthropic>=0.40.0
playwright>=1.40.0
requests>=2.31.0
python-dotenv>=1.0.0
Pillow>=10.0.0
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.2.0
sendgrid>=6.11.0
fastmcp>=0.1.0
pytest>=7.4.0
```

## STEP 6: BUILD MCP SERVER 1 — PLAYWRIGHT RESEARCH

### mcp_servers/playwright_research.py

Build a FastMCP server with these tools:

**Tool 1: `get_trending_topics(niche: str, count: int = 10) -> str`**
- Opens headless Chromium browser
- Goes to YouTube search for variations of the niche:
  - "{niche}", "{niche} 2026", "{niche} tutorial", "how to {niche}", "best {niche}"
- Extracts video titles from search results
- Returns JSON list of trending topic ideas
- Always closes browser in finally block

**Tool 2: `analyze_competitor(channel_url: str) -> str`**
- Opens the channel's /videos page
- Extracts last 10 video titles + view metadata
- Returns JSON with video list and patterns
- Always closes browser in finally block

**Tool 3: `find_content_gaps(topic: str) -> str`**
- Searches YouTube for variations:
  - "{topic} how to", "{topic} beginner", "{topic} mistakes", "{topic} vs", "{topic} worth it"
- Counts results per query
- Returns JSON with opportunity scores (HIGH if < 5 results, MEDIUM otherwise)
- Always closes browser in finally block

**Tool 4: `get_search_suggestions(seed: str) -> str`**
- Uses YouTube's search suggestion API endpoint
- Fetches autocomplete suggestions for the seed query
- Returns JSON list of suggestions (these are what people actually search for)

**Important implementation notes:**
- All tools use `async with async_playwright() as p:` context manager
- Always launch with `headless=True`
- Use `wait_for_timeout(2000)` after page loads for dynamic content
- Wrap everything in try/except/finally to ensure browser closes
- Return JSON strings from all tools
- Run with `mcp.run(transport="stdio")`

## STEP 7: BUILD MCP SERVER 2 — CONTENT GENERATION

### mcp_servers/content_gen.py

Build a FastMCP server with these tools:

**Tool 1: `generate_script(topic: str, series: str, duration_minutes: int = 10) -> str`**
- Uses Anthropic SDK with model `claude-sonnet-4-20250514`
- `series` parameter: "build_log", "tool_review", or "tutorial"
- Loads the matching template from templates/ directory for structure guidance
- Word count target: duration_minutes * 150 (150 words/min for voiceover)
- System prompt enforces the video structure from CLAUDE.md:
  - HOOK (bold claim, no "hey guys")
  - CONTEXT
  - CONTENT (3-5 key points)
  - RESULTS
  - CTA
- Includes [PAUSE] markers for natural speech breaks
- Saves script to content/queue/script_{safe_topic}_{date}.txt
- Tracks token usage and cost: input_tokens * $3/M + output_tokens * $15/M (Sonnet pricing)
- Returns JSON with script_path, word_count, estimated_duration, cost_usd

**Tool 2: `generate_voiceover(script_path: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> str`**
- Reads script file, replaces [PAUSE] with "..." for natural pauses
- Calls ElevenLabs API: POST /v1/text-to-speech/{voice_id}
- Uses model `eleven_turbo_v2_5` (fastest, cheapest)
- Voice settings: stability=0.5, similarity_boost=0.75, style=0.3
- Saves audio to content/queue/audio_{safe_topic}_{date}.mp3
- Gets duration via ffprobe
- Returns JSON with audio_path, duration_seconds, characters_used

**Tool 3: `assemble_video(audio_path: str, topic: str) -> str`**
- Gets audio duration via ffprobe
- Downloads 5 HD stock video clips from Pexels API for the topic
- Creates a concat file listing all clips
- Uses FFmpeg to:
  - Concatenate stock clips
  - Overlay the audio track
  - Trim to match audio duration with `-shortest`
  - Output 1920x1080 H.264 MP4
- Fallback if no Pexels key: solid dark background (#0a0a0f) with audio
- Saves to content/queue/video_{safe_topic}_{date}.mp4
- Returns JSON with video_path, duration_seconds, resolution, cost_usd (always $0)

**Tool 4: `generate_thumbnail(topic: str, title_text: str) -> str`**
- Uses Pillow to create 1280x720 thumbnail
- Design:
  - Dark gradient background (#0a0a12 → #0a1628)
  - Horizontal cyan accent line at 60% height
  - Title text in bold white, max 2 lines, large font
  - "SHARKWAVE AI" in smaller text at bottom in cyan
  - Subtle grid pattern overlay for tech feel
  - Corner bracket accents in cyan
- Saves to content/queue/thumb_{safe_topic}_{date}.png
- Returns JSON with thumbnail_path, resolution, cost_usd ($0)

**Tool 5: `generate_metadata(topic: str, series: str, script_path: str) -> str`**
- Uses Claude Sonnet to generate SEO metadata
- Reads first 500 chars of script for context
- Prompt asks for JSON only (no markdown):
  - title: Under 60 chars, keyword front-loaded
  - description: 200 words with keywords + timestamps placeholder + CTA + disclaimer
  - tags: Up to 15 relevant tags
  - category: YouTube category ID
- Auto-adds to description:
  - "🦈 Subscribe for more: @SharkWaveAI"
  - "🔗 GitHub: github.com/saijayanth888/shark-trading-agent"
  - "⚠️ Not financial advice. Educational content only."
- Saves to content/queue/meta_{safe_topic}_{date}.json
- Returns JSON with metadata_path, title, tags_count, cost_usd

**Tool 6: `create_video_package(topic: str, series: str, duration_minutes: int = 10) -> str`**
- THIS IS THE MASTER FUNCTION — runs the full pipeline:
  1. generate_script()
  2. generate_voiceover()
  3. assemble_video()
  4. generate_thumbnail()
  5. generate_metadata()
- Creates a manifest.json in content/queue/ with all file paths
- Logs total cost to logs/cost-log.csv
- Returns JSON summary of the complete package

## STEP 8: BUILD MCP SERVER 3 — YOUTUBE API

### mcp_servers/youtube_api.py

Build a FastMCP server with these tools:

**Tool 1: `upload_video(video_path, title, description, tags, category_id, privacy, publish_at) -> str`**
- Uses google-api-python-client
- Reads OAuth token from YOUTUBE_TOKEN_PATH
- Creates video resource with:
  - snippet: title (max 100 chars), description, tags (max 15), categoryId
  - status: privacyStatus, selfDeclaredMadeForKids=False, containsSyntheticMedia=True
  - If publish_at provided: set as scheduled publish
- Uses MediaFileUpload with resumable=True
- Returns JSON with video_id, url, title, status, scheduled time

**Tool 2: `set_thumbnail(video_id: str, thumbnail_path: str) -> str`**
- Uploads custom thumbnail for a video
- Returns JSON confirmation

**Tool 3: `get_channel_analytics(days: int = 7) -> str`**
- Gets channel statistics: subscribers, total views, video count
- Gets last 10 videos with view counts and likes
- Returns JSON summary

**Tool 4: `add_to_playlist(video_id: str, playlist_id: str) -> str`**
- Adds video to specified playlist
- Returns JSON confirmation

**Tool 5: `create_playlist(title: str, description: str) -> str`**
- Creates a new playlist on the channel
- Returns JSON with playlist_id

**Important implementation notes for YouTube API server:**
- Helper function `get_youtube_service()` handles authentication
- Reads token from YOUTUBE_TOKEN_PATH
- If token expired, refreshes automatically
- If no token exists, raises RuntimeError telling user to run oauth_setup.py
- NEVER use Playwright/browser automation for YouTube operations

## STEP 9: CREATE OAUTH SETUP SCRIPT

### oauth_setup.py

Simple script that:
1. Checks for client_secrets.json at YOUTUBE_CLIENT_SECRETS_PATH
2. If missing, prints instructions for Google Cloud Console setup
3. Runs InstalledAppFlow.from_client_secrets_file() with scopes:
   - youtube.upload
   - youtube
   - youtube.readonly
4. Opens browser for user to authorize
5. Saves token to YOUTUBE_TOKEN_PATH
6. Prints confirmation message

## STEP 10: CREATE CONTENT TEMPLATES

### templates/script_trading_update.txt
```
SERIES: Shark Agent Build Log
STRUCTURE:
- HOOK: Start with this week's P&L number. "My AI trading agent made/lost $X this week."
- RECAP: What positions the agent held, what it bought/sold
- DECISIONS: Walk through 1-2 key trade decisions. Show the bull vs bear debate.
- WHAT BROKE: Be honest about failures. Did the agent make bad calls? Why?
- WHAT IMPROVED: Any strategy adjustments from the weekly review
- NEXT WEEK: What the agent is watching
- CTA: "Subscribe to see if the shark survives next week"
- DISCLAIMER: "This is not financial advice. I'm documenting an experiment."
```

### templates/script_tool_review.txt
```
SERIES: Tool Teardowns
STRUCTURE:
- HOOK: "I spent X hours with [tool] so you don't have to."
- WHAT IT IS: Brief explanation for beginners
- SETUP: How to get started (speed through this)
- THE GOOD: 2-3 things that genuinely impressed you
- THE BAD: 2-3 real problems or limitations
- VS ALTERNATIVES: Brief comparison to competitors
- VERDICT: Would you use this daily? Is it worth the price?
- CTA: "Subscribe for more honest AI tool reviews"
```

### templates/script_tutorial.txt
```
SERIES: Build With AI
STRUCTURE:
- HOOK: Show the finished result first. "Here's what we're building today."
- PREREQUISITES: What you need before starting (keep brief)
- STEP-BY-STEP: Walk through the build. Show real code, real terminal, real errors.
- GOTCHAS: Things that tripped you up (save others the pain)
- FINAL RESULT: Demo the working system
- EXTEND IT: Quick ideas for how viewer can customize
- CTA: "Code is on GitHub. Link in description. Subscribe for the next build."
```

## STEP 11: CREATE CONFIG FILES

### config/voices.json
```json
{
  "default": {
    "voice_id": "21m00Tcm4TlvDq8ikWAM",
    "name": "Rachel",
    "description": "Professional, clear, neutral American English"
  },
  "alternative_voices": [
    {
      "voice_id": "EXAVITQu4vr4xnSDxMaL",
      "name": "Bella",
      "description": "Warm, conversational"
    },
    {
      "voice_id": "ErXwobaYiN019PkySvjV",
      "name": "Antoni",
      "description": "Male, professional"
    }
  ]
}
```

### config/niches.json
```json
{
  "primary_niches": [
    {
      "name": "AI Trading",
      "keywords": ["AI trading bot", "AI trading agent", "algorithmic trading AI", "Claude trading", "Alpaca trading bot"],
      "competitors": [
        "https://www.youtube.com/@hackingthemarkets",
        "https://www.youtube.com/@NicholasRenotte"
      ]
    },
    {
      "name": "AI Tools",
      "keywords": ["Claude Code", "Devin AI", "AI coding tools", "MCP servers", "AI automation"],
      "competitors": []
    },
    {
      "name": "AI Automation",
      "keywords": ["AI passive income", "AI automation money", "automate with AI", "AI agent build"],
      "competitors": []
    }
  ]
}
```

### config/schedule.json
```json
{
  "timezone": "America/New_York",
  "publish_slots": [
    {"day": "Monday", "time": "10:00", "series": "tool_review"},
    {"day": "Wednesday", "time": "10:00", "series": "tutorial"},
    {"day": "Friday", "time": "10:00", "series": "build_log"}
  ],
  "batch_day": "Sunday",
  "batch_time": "20:00"
}
```

## STEP 12: CREATE THE 2 ROUTINE PROMPT FILES

### routines/content-factory.md

```markdown
# Content Factory — Daily Routine
# Cron: 0 5 * * 1-5 (5:00 AM ET, Mon-Fri)
# Runs: Monday through Friday

## Instructions

You are the Shark Content Factory. Your job is to produce ONE video package per run.

### Step 1: Determine Today's Content
- Read config/schedule.json to find today's series type
- Monday = tool_review, Wednesday = tutorial, Friday = build_log

### Step 2: Research Topic
- Use playwright-research MCP:
  - Call get_trending_topics() with the niche matching today's series
  - Call find_content_gaps() for the top trending topic
  - Pick the topic with the best opportunity score
- For Friday build_log: topic is always "Shark Agent Week [N] P&L Update"
  - Read ../shark-trading-agent/memory/WEEKLY-REVIEW.md for data if available

### Step 3: Produce Video Package
- Use content-gen MCP:
  - Call create_video_package() with the chosen topic and series type
  - This runs the full pipeline: script → voice → video → thumbnail → metadata

### Step 4: Verify Output
- Check that content/queue/ has all 5 files:
  - script_*.txt
  - audio_*.mp3
  - video_*.mp4
  - thumb_*.png
  - meta_*.json
  - manifest.json
- Verify manifest.json contains all file paths

### Step 5: Cost Check
- Read logs/cost-log.csv
- Sum this month's total
- If monthly total > $10: STOP producing and log warning
- Otherwise: log today's cost

### Step 6: Commit
- Git add all new files in content/queue/
- Commit with message: "content: {series} — {topic} [{date}]"

### IMPORTANT
- ONE video per day maximum
- If any step fails, log the error and skip — don't retry endlessly
- Never exceed budget cap
```

### routines/weekly-batch-publish.md

```markdown
# Weekly Batch Publish — Sunday Routine
# Cron: 0 20 * * 0 (8:00 PM ET, Sunday)
# Runs: Every Sunday evening

## Instructions

You are the Shark Content Publisher. Upload this week's queued
videos and schedule them for the upcoming week.

### Step 1: Read Queue
- List all manifest.json files in content/queue/
- Parse each one to get video_path, thumbnail_path, metadata
- Sort by series: build_log first (Friday), then others

### Step 2: Map to Publishing Schedule
- Read config/schedule.json
- Assign each video to its scheduled slot:
  - Video 1 → Monday 10:00 AM ET
  - Video 2 → Wednesday 10:00 AM ET
  - Video 3 → Friday 10:00 AM ET
- Convert times to ISO 8601 UTC for the YouTube API

### Step 3: Upload Each Video
For each video, use youtube-api MCP:
1. Call upload_video() with:
   - video_path from manifest
   - title, description, tags from meta_*.json
   - privacy="private"
   - publish_at = scheduled ISO datetime
2. Call set_thumbnail() with the video_id + thumb_*.png
3. If a playlist exists for the series, call add_to_playlist()

### Step 4: Archive
- Move all processed files from content/queue/ to content/published/{date}/
- Clear content/queue/ for next week

### Step 5: Log & Notify
- Append to logs/publish-log.csv: date, title, video_id, scheduled_time
- If SENDGRID_API_KEY is set, send email summary:
  - Videos uploaded this week
  - Scheduled publish times
  - Total cost this month
  - Channel analytics snapshot

### Step 6: Commit
- Commit with message: "publish: batch upload {date} — {N} videos scheduled"

### IMPORTANT
- Set containsSyntheticMedia: true on EVERY upload (YouTube 2026 policy)
- Never upload more than 6 videos in one batch (API rate limits)
- If upload fails, log error and continue with remaining videos
- Always add disclaimer text to description
```

## STEP 13: SEED LOG FILES

### logs/cost-log.csv
```csv
date,topic,series,script_cost,voice_cost,video_cost,thumbnail_cost,metadata_cost,total_cost
```

### logs/publish-log.csv
```csv
date,title,series,video_id,youtube_url,scheduled_time,status
```

## STEP 14: CREATE TESTS

### tests/test_script_gen.py
Test script generation:
- Test that generate_script returns valid JSON
- Test that script word count is within 80-120% of target
- Test that script contains [PAUSE] markers
- Test that script does NOT start with "hey guys" or "what's up"
- Test cost tracking (should be < $0.20 per script)

### tests/test_metadata.py
Test metadata generation:
- Test that title is under 60 characters
- Test that tags list has 5-15 items
- Test that description contains the disclaimer text
- Test that description contains GitHub link

### tests/test_thumbnail.py
Test thumbnail creation:
- Test output image is 1280x720
- Test output is valid PNG
- Test file size is reasonable (< 2MB for YouTube upload limit)

## STEP 15: UPDATE README.md

Write a clean README with:
- Project description: "Automated YouTube content factory for @SharkWaveAI"
- Architecture diagram (text-based: Research MCP → Content Gen MCP → YouTube API MCP)
- Setup instructions (env vars, OAuth, playwright install)
- How to run manually vs. automated routines
- Cost breakdown table
- Link to YouTube channel and companion trading agent repo

## FINAL INSTRUCTIONS

1. Create ALL files with real, working Python code — not placeholders
2. Every MCP server tool must have docstrings, type hints, error handling, try/except/finally
3. All Playwright usage must close the browser in a finally block
4. Cost tracking must happen on EVERY API call — append to cost-log.csv
5. Shell scripts must be executable (chmod +x)
6. After creating everything, run: `pip install -r requirements.txt`
7. Run: `playwright install chromium` to install the browser
8. Run: `pytest tests/ -v` to verify tests pass
9. Commit everything with message: "feat: scaffold Shark Content Factory v0.1 — full pipeline"

Build order: CLAUDE.md → config files → MCP servers (research, content, youtube) → routines → templates → tests → README. Go.
```
