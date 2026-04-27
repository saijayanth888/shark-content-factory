"""
Shark Content Factory — Legal & Compliance MCP Server

FastMCP server providing tools for:
- YouTube AI disclosure compliance checking
- Content copyright pre-scanning
- Asset provenance verification
- Financial disclaimer enforcement
- Full compliance report generation

Enforces YouTube 2025 "Inauthentic Content" rules, July 2025 AI Slop
crackdown criteria, and AI disclosure requirements.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# --- Production config ---
_ENV = os.getenv("ENVIRONMENT", "development")


def mask_error_details(error: Exception) -> str:
    if _ENV == "production":
        return f"Internal error in legal_compliance [{type(error).__name__}]"
    return str(error)


mcp = FastMCP(
    "legal-compliance",
    **({"log_level": "WARNING"} if _ENV == "production" else {}),
)

CONTENT_DIR = Path(__file__).parent.parent / "content"
CONFIG_DIR = Path(__file__).parent.parent / "config"
QUEUE_DIR = CONTENT_DIR / "queue"
SHORTS_DIR = CONTENT_DIR / "shorts"

# --- Centralized URL config ---
_URLS_PATH = CONFIG_DIR / "urls.json"
_URL_CONFIG = json.loads(_URLS_PATH.read_text()) if _URLS_PATH.exists() else {}
YOUTUBE_POLICY_REF_URL = _URL_CONFIG.get("references", {}).get(
    "youtube_policy", "https://support.google.com/youtube/answer/1311392"
)


@mcp.tool()
def policy_compliance_check(script_path: str, metadata_path: str = "") -> str:
    """Validate content against YouTube 2025 policies BEFORE publishing.

    Checks performed:
    - Minimum quality threshold (word count)
    - Original commentary markers (human creative input)
    - Financial disclaimer presence (for trading content)
    - AI disclosure language
    - Spam / CTA overload detection
    - Near-duplicate content detection
    - July 2025 "AI Slop" demonetization criteria
    - Metadata validation (title length, tag count, clickbait)

    Args:
        script_path: Path to the script file
        metadata_path: Path to metadata JSON (optional)

    Returns:
        JSON with compliance_status (PASS/FAIL/WARN), issues, warnings,
        originality_score, checks_passed, recommendation
    """
    issues = []
    warnings = []

    sp = Path(script_path)
    if not sp.exists():
        return json.dumps({"error": f"Script not found: {script_path}"})
    script = sp.read_text()
    word_count = len(script.split())

    # --- Check 1: Minimum quality ---
    if word_count < 200:
        issues.append("Script too short (<200 words). YouTube flags as low-quality.")
    if word_count < 500:
        warnings.append("Script under 500 words. Add more depth for retention.")

    # --- Check 2: Original commentary ---
    analysis_markers = [
        "i think", "in my experience", "what i found", "here's why",
        "let me explain", "the key insight", "what most people miss",
        "my recommendation", "based on my testing", "i discovered",
        "i built", "i noticed", "my approach", "what worked for me",
    ]
    has_original = sum(1 for m in analysis_markers if m in script.lower())
    if has_original == 0:
        issues.append(
            "No original commentary detected. YouTube requires 'meaningful "
            "original content.' Add personal analysis or unique perspectives."
        )
    elif has_original < 3:
        warnings.append(
            f"Low originality signal ({has_original} markers). "
            "Add more personal insights to avoid July 2025 demonetization."
        )

    # --- Check 3: Financial disclaimer ---
    disclaimer_markers = [
        "not financial advice", "educational", "results may vary",
        "do your own research", "disclaimer", "past performance",
    ]
    has_disclaimer = any(m in script.lower() for m in disclaimer_markers)
    trading_markers = ["trading", "invest", "stock", "profit", "return", "portfolio"]
    is_financial = any(m in script.lower() for m in trading_markers)

    if is_financial and not has_disclaimer:
        issues.append(
            "Financial content detected but NO disclaimer found. REQUIRED: "
            "'Not financial advice. Educational content only. Results may vary.'"
        )

    # --- Check 4: AI disclosure in script ---
    ai_disclosure_markers = [
        "ai-generated", "ai generated", "created with ai", "synthetic",
        "ai-assisted", "ai assisted", "artificial intelligence",
        "generated using", "produced with ai",
    ]
    has_ai_mention = any(m in script.lower() for m in ai_disclosure_markers)
    if not has_ai_mention:
        warnings.append(
            "No AI disclosure language in script. Ensure the YouTube upload "
            "has 'Altered/Synthetic Content' toggle enabled."
        )

    # --- Check 5: Spam indicators ---
    spam_phrases = [
        "subscribe and like", "smash that like button",
        "don't forget to subscribe", "hit the bell",
        "leave a comment below",
    ]
    spam_count = sum(1 for p in spam_phrases if p in script.lower())
    if spam_count > 2:
        warnings.append(
            f"Excessive CTA spam ({spam_count} instances). Keep to 1-2 CTAs max."
        )

    # --- Check 6: Duplicate content ---
    for d in [QUEUE_DIR, SHORTS_DIR]:
        if not d.exists():
            continue
        for f in list(d.glob("script_*.txt"))[:5]:
            if f == sp:
                continue
            try:
                existing_text = f.read_text()
                script_words = set(script.lower().split())
                existing_words = set(existing_text.lower().split())
                if len(script_words) > 0:
                    overlap = len(script_words & existing_words) / len(script_words)
                    if overlap > 0.7:
                        issues.append(
                            f"High content overlap ({overlap:.0%}) with {f.name}. "
                            "YouTube penalizes near-duplicate content."
                        )
            except Exception:
                continue

    # --- Check 7: AI Slop criteria ---
    ai_slop_flags = []
    if word_count < 300 and "short" not in script_path.lower():
        ai_slop_flags.append(
            "Very short long-form script — may be flagged as AI-generated filler"
        )
    generic_phrases = [
        "in this video we will", "today we're going to",
        "without further ado", "let's dive right in",
        "in conclusion", "thanks for watching",
    ]
    generic_count = sum(1 for p in generic_phrases if p in script.lower())
    if generic_count > 3:
        ai_slop_flags.append(
            f"High generic phrase count ({generic_count}). "
            "YouTube's AI detection may flag this as template content."
        )
    for flag in ai_slop_flags:
        warnings.append(f"[AI SLOP RISK] {flag}")

    # --- Check 8: Metadata validation ---
    if metadata_path:
        mp = Path(metadata_path)
        if mp.exists():
            try:
                meta = json.loads(mp.read_text())
                title = meta.get("title", "")
                if len(title) > 100:
                    issues.append(f"Title too long ({len(title)} chars, max 100)")
                if len(title) < 20:
                    warnings.append("Title too short. Aim for 40-60 chars for optimal CTR.")
                tags = meta.get("tags", [])
                if len(tags) > 15:
                    warnings.append(f"Too many tags ({len(tags)}). YouTube recommends 10-15.")
                if len(tags) < 5:
                    warnings.append("Too few tags. Add 10-15 relevant tags.")
                clickbait = [
                    "you won't believe", "shocking", "insane",
                    "100%", "guaranteed",
                ]
                for cb in clickbait:
                    if cb in title.lower():
                        warnings.append(
                            f"Potential clickbait in title: '{cb}'. May reduce trust."
                        )
            except json.JSONDecodeError:
                warnings.append("Could not parse metadata JSON.")

    # --- Verdict ---
    status = "PASS"
    if issues:
        status = "FAIL"
    elif warnings:
        status = "WARN"

    return json.dumps({
        "compliance_status": status,
        "issues": issues,
        "warnings": warnings,
        "originality_score": min(has_original * 2, 10),
        "word_count": word_count,
        "checks_passed": {
            "minimum_quality": word_count >= 200,
            "original_commentary": has_original >= 3,
            "financial_disclaimer": has_disclaimer if is_financial else True,
            "no_duplicate_content": not any("overlap" in i for i in issues),
            "cta_not_spammy": spam_count <= 2,
            "no_ai_slop_flags": len(ai_slop_flags) == 0,
        },
        "ai_disclosure_checklist": {
            "script_mentions_ai": has_ai_mention,
            "upload_synthetic_toggle": "MUST be enabled during YouTube upload",
            "description_disclaimer": "MUST include AI disclosure in description",
        },
        "recommendation": (
            "SAFE TO PUBLISH" if status == "PASS"
            else "FIX ISSUES BEFORE PUBLISHING" if status == "FAIL"
            else "REVIEW WARNINGS — proceed with caution"
        ),
        "youtube_policy_ref": YOUTUBE_POLICY_REF_URL,
    })


@mcp.tool()
def ai_disclosure_check(
    video_title: str,
    description: str,
    has_ai_voiceover: bool = True,
    has_ai_script: bool = True,
    has_stock_footage: bool = True,
    has_ai_thumbnail: bool = True,
) -> str:
    """Pre-upload AI disclosure checklist.

    Validates that all YouTube AI disclosure requirements are met BEFORE
    uploading. Returns a checklist with pass/fail for each item.

    Args:
        video_title: Planned video title
        description: Planned video description
        has_ai_voiceover: Whether video uses AI-generated voice
        has_ai_script: Whether script was AI-generated/assisted
        has_stock_footage: Whether video uses stock footage
        has_ai_thumbnail: Whether thumbnail was AI-generated

    Returns:
        JSON with checklist, overall_pass, required_actions
    """
    checklist = []
    required_actions = []
    desc_lower = description.lower()

    # 1. Synthetic media toggle (cannot be set via API)
    checklist.append({
        "item": "YouTube Studio 'Altered/Synthetic Content' toggle",
        "status": "ACTION REQUIRED",
        "note": "Must be enabled during upload — cannot be automated via API",
    })
    required_actions.append(
        "Enable 'Altered/Synthetic Content' in YouTube Studio during upload"
    )

    # 2. Description disclaimer
    has_ai_disclosure = any(
        phrase in desc_lower
        for phrase in [
            "ai-generated", "ai generated", "artificial intelligence",
            "created with ai", "ai-assisted", "synthetic",
        ]
    )
    checklist.append({
        "item": "AI disclosure in description",
        "status": "PASS" if has_ai_disclosure else "FAIL",
        "note": (
            "Found AI disclosure" if has_ai_disclosure
            else "Description must mention AI usage"
        ),
    })
    if not has_ai_disclosure:
        required_actions.append(
            "Add to description: 'AI DISCLOSURE: This video contains AI-generated "
            "voiceover and AI-assisted script writing. All content reviewed and "
            "approved by human creator.'"
        )

    # 3. Financial disclaimer
    financial_keywords = [
        "trading", "invest", "stock", "profit", "money", "portfolio",
    ]
    is_financial = any(
        kw in video_title.lower() or kw in desc_lower
        for kw in financial_keywords
    )
    has_fin_disclaimer = any(
        phrase in desc_lower
        for phrase in ["not financial advice", "educational", "results may vary"]
    )
    if is_financial:
        checklist.append({
            "item": "Financial disclaimer",
            "status": "PASS" if has_fin_disclaimer else "FAIL",
            "note": "Required for all trading/investment content",
        })
        if not has_fin_disclaimer:
            required_actions.append(
                "Add to description: 'DISCLAIMER: Not financial advice. "
                "Educational content only. Past performance does not guarantee "
                "future results.'"
            )

    # 4. Asset-specific disclosures
    if has_ai_voiceover:
        checklist.append({
            "item": "AI voiceover disclosure",
            "status": "PASS" if ("ai" in desc_lower and "voice" in desc_lower) else "WARN",
            "note": "Recommended: mention AI voiceover in description",
        })
    if has_stock_footage:
        checklist.append({
            "item": "Stock footage attribution",
            "status": "PASS",
            "note": "Pexels license: free for commercial use, no attribution required",
        })

    # 5. Title check
    misleading = ["guaranteed", "100%", "you won't believe", "secret"]
    title_issues = [m for m in misleading if m in video_title.lower()]
    checklist.append({
        "item": "Title not misleading",
        "status": "FAIL" if title_issues else "PASS",
        "note": (
            f"Misleading terms found: {title_issues}" if title_issues
            else "Title is compliant"
        ),
    })
    if title_issues:
        required_actions.append(f"Remove misleading terms from title: {title_issues}")

    overall_pass = not any(item["status"] == "FAIL" for item in checklist)

    return json.dumps({
        "overall_pass": overall_pass,
        "checklist": checklist,
        "required_actions": required_actions,
        "upload_reminder": {
            "containsSyntheticMedia": True,
            "selfDeclaredMadeForKids": False,
            "license": "youtube",
        },
    })


@mcp.tool()
def copyright_precheck(asset_sources: list[dict]) -> str:
    """Pre-scan planned assets for copyright issues.

    Validates that all assets are properly licensed before production.

    Args:
        asset_sources: List of dicts with keys:
            - type: script, voiceover, footage, music, thumbnail
            - source: anthropic, elevenlabs, pexels, original, other
            - details: Additional info (Pexels video ID, voice name, etc.)

    Returns:
        JSON with copyright_status (CLEAR/FLAGGED), per-asset results,
        content_id_risk, dmca_risk
    """
    results = []
    flagged = False

    for asset in asset_sources:
        asset_type = asset.get("type", "unknown")
        source = asset.get("source", "unknown")
        details = asset.get("details", "")

        status = "CLEAR"
        notes = ""
        license_type = ""

        if source == "pexels":
            license_type = "Pexels License (free commercial use)"
            notes = "No attribution required. Cannot sell as-is."
        elif source == "anthropic":
            license_type = "Anthropic API TOS"
            notes = "Output owned by user per Anthropic TOS. Must disclose AI generation."
        elif source == "elevenlabs":
            license_type = "ElevenLabs TOS"
            if "clone" in details.lower():
                status = "FLAGGED"
                flagged = True
                notes = (
                    "Voice cloning of real people requires explicit consent. "
                    "Verify permissions."
                )
            else:
                notes = "Stock voices are clear for commercial use."
        elif source == "original":
            license_type = "Original Work"
            notes = "Self-created content — full copyright ownership."
        else:
            status = "FLAGGED"
            flagged = True
            notes = "Unknown source — verify licensing before use."
            license_type = "UNKNOWN — verify"

        results.append({
            "asset_type": asset_type,
            "source": source,
            "details": details,
            "status": status,
            "license": license_type,
            "notes": notes,
        })

    return json.dumps({
        "copyright_status": "FLAGGED" if flagged else "CLEAR",
        "assets_checked": len(results),
        "results": results,
        "content_id_risk": (
            "LOW — all assets are original or properly licensed" if not flagged
            else "MEDIUM — flagged assets need manual review"
        ),
        "dmca_risk": "LOW" if not flagged else "MEDIUM",
    })


@mcp.tool()
def generate_compliance_report(
    topic: str,
    script_path: str,
    metadata_path: str = "",
    video_id: str = "pending",
) -> str:
    """Generate a full legal compliance report for a video.

    Combines policy check + copyright check into a single comprehensive
    report. This is what the Legal & Quality Agent runs before approving.

    Args:
        topic: Video topic
        script_path: Path to script
        metadata_path: Path to metadata JSON
        video_id: YouTube video ID (or 'pending')

    Returns:
        JSON with full compliance report and final verdict
    """
    policy_result = json.loads(policy_compliance_check(script_path, metadata_path))

    default_assets = [
        {"type": "script", "source": "anthropic", "details": "claude-sonnet-4-20250514"},
        {"type": "voiceover", "source": "elevenlabs", "details": "Rachel stock voice"},
        {"type": "footage", "source": "pexels", "details": "stock video search"},
        {"type": "thumbnail", "source": "anthropic", "details": "Pillow-generated with AI text"},
    ]
    copyright_result = json.loads(copyright_precheck(default_assets))

    policy_ok = policy_result.get("compliance_status") != "FAIL"
    copyright_ok = copyright_result.get("copyright_status") == "CLEAR"

    if policy_ok and copyright_ok:
        verdict = "✅ APPROVED"
        recommendation = (
            "Content is compliant. Safe to publish with AI disclosure toggle enabled."
        )
    elif not policy_ok:
        verdict = "❌ REJECTED"
        recommendation = "Fix policy issues before publishing."
    else:
        verdict = "⚖️ LEGAL HOLD"
        recommendation = "Copyright concerns detected. Manual review required."

    return json.dumps({
        "topic": topic,
        "video_id": video_id,
        "verdict": verdict,
        "recommendation": recommendation,
        "policy_compliance": policy_result,
        "copyright_check": copyright_result,
        "required_upload_settings": {
            "containsSyntheticMedia": True,
            "selfDeclaredMadeForKids": False,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
