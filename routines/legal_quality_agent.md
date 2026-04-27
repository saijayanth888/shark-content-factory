# Legal & Quality Agent Routine — Compliance Gate

> **Schedule:** Triggered after production agent sets status to `🔨 PRODUCED`
> **Agent Role:** Legal & Quality Agent — Reviews and approves/rejects content
> **MCP Servers:** `legal-compliance`, `sheets-api`

## Objective

Review all produced content for legal compliance, copyright clearance, and
quality standards before approving for publication. This agent acts as the
quality gate — nothing gets published without passing through here.

## Workflow

### Step 1: Read Produced Content from Calendar

Call `read_calendar` from `sheets-api` with status filter:

```
read_calendar(status_filter="🔨 PRODUCED")
```

For each item returned, perform Steps 2-5.

### Step 2: Run Policy Compliance Check

Call `policy_compliance_check` from `legal-compliance`:

```
policy_compliance_check(
    script_path="<script_path from calendar>",
    metadata_path="<metadata_path if available>"
)
```

Record the `compliance_status` (PASS/FAIL/WARN).

### Step 3: Run Copyright Pre-Check

Call `copyright_precheck` from `legal-compliance` with the assets used:

```
copyright_precheck(asset_sources=[
    {"type": "script", "source": "anthropic", "details": "claude-sonnet-4-20250514"},
    {"type": "voiceover", "source": "elevenlabs", "details": "Rachel stock voice"},
    {"type": "footage", "source": "pexels", "details": "stock video"},
    {"type": "thumbnail", "source": "anthropic", "details": "Pillow-generated"}
])
```

### Step 4: Run AI Disclosure Check

Call `ai_disclosure_check` from `legal-compliance`:

```
ai_disclosure_check(
    video_title="<title>",
    description="<description>",
    has_ai_voiceover=true,
    has_ai_script=true,
    has_stock_footage=true,
    has_ai_thumbnail=true
)
```

### Step 5: Update Status Based on Verdict

**If all checks PASS:**

Call `update_content_status` from `sheets-api`:

```
update_content_status(
    topic="<topic>",
    date="<date>",
    new_status="✅ APPROVED",
    agent="legal_quality_agent",
    notes="All compliance checks passed"
)
```

**If any check FAILS:**

```
update_content_status(
    topic="<topic>",
    date="<date>",
    new_status="❌ REJECTED",
    agent="legal_quality_agent",
    notes="<specific failure reasons>"
)
```

**If WARN only (no FAIL):**

```
update_content_status(
    topic="<topic>",
    date="<date>",
    new_status="⚖️ IN REVIEW",
    agent="legal_quality_agent",
    notes="Warnings need human review: <warning details>"
)
```

### Step 6: Log Asset Provenance

For each approved video, call `log_asset_provenance` from `sheets-api` for
every asset used:

```
log_asset_provenance(
    video_id="pending",
    asset_type="script",
    source="anthropic",
    model_version="claude-sonnet-4-20250514",
    ai_disclosure="required",
    copyright_status="clear"
)
```

### Step 7: Audit Trail

Call `log_audit_event` from `sheets-api`:

```
log_audit_event(
    agent="legal_quality_agent",
    action="COMPLIANCE_REVIEW",
    details="Reviewed N items: X approved, Y rejected, Z in review"
)
```

## Approval Criteria (ALL must pass)

1. Policy compliance status is not FAIL
2. Copyright status is CLEAR for all assets
3. AI disclosure checklist has no FAIL items
4. Script word count >= 200 (long-form) or >= 50 (short)
5. Financial disclaimer present if financial content detected
6. No duplicate content detected (overlap < 70%)

## Human Escalation

Items set to `⚖️ IN REVIEW` require human decision. The human creator
should review the warnings in the Google Sheet and manually change status
to either `✅ APPROVED` or `❌ REJECTED`.
