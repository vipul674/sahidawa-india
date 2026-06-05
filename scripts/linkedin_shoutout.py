#!/usr/bin/env python3
"""
SahiDawa LinkedIn Automated Shoutout Script (via Make.com Webhook)
===================================================================
Flow:
  1. PR is merged with level:advanced or level:critical label
  2. GitHub Actions calls this script
  3. Script generates a unique post using Gemini AI
  4. Script sends the post as JSON to a Make.com webhook
  5. Make.com posts it to LinkedIn Company Page (no Advertising API needed)

Environment Variables Required (set as GitHub Secrets):
  - MAKE_WEBHOOK_URL  : Make.com webhook URL (https://hook.eu1.make.com/...)
  - GEMINI_API_KEY    : Google Gemini API key
  - PR_TITLE          : Title of the merged PR
  - PR_AUTHOR         : GitHub username of the contributor
  - PR_URL            : URL of the merged PR
  - PR_LABELS         : Comma-separated labels on the PR
  - PR_BODY           : Description/body of the merged PR (optional)
  - PR_NUMBER         : PR number
  - PR_REPO           : Repository name (e.g. RatLoopz/sahidawa-india)
  - PR_LINES_CHANGED  : Total lines added + deleted in the PR
"""

import os
import sys
import re
import json
import requests

# ─────────────────────────────────────────────────────────────────────────────
# PROJECT CONFIG — Edit these to change branding
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_NAME = "SahiDawa"
PROJECT_TAGLINE = "India's open-source medicine safety platform for 1.4 billion people 🇮🇳"
PROJECT_GITHUB_URL = "https://github.com/RatLoopz/sahidawa-india"
PROJECT_HASHTAGS = "#SahiDawa #OpenSource #GSSoC2026 #BuildForIndia #HealthTech #IndiaStack"

LABEL_TIER_MAP = {
    "level:critical": ("⚡ Critical-Level", "mission-critical"),
    "level:advanced": ("🔥 Advanced-Level", "highly complex"),
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_env_or_exit(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"❌ ERROR: Required environment variable '{key}' is missing or empty.")
        sys.exit(1)
    return val


def get_pr_metadata() -> dict:
    return {
        "title": get_env_or_exit("PR_TITLE"),
        "author": get_env_or_exit("PR_AUTHOR"),
        "url": get_env_or_exit("PR_URL"),
        "number": os.environ.get("PR_NUMBER", "N/A"),
        "labels": os.environ.get("PR_LABELS", ""),
        "body": os.environ.get("PR_BODY", "").strip()[:500],
        "repo": os.environ.get("PR_REPO", "RatLoopz/sahidawa-india"),
        "lines_changed": os.environ.get("PR_LINES_CHANGED", "0"),
    }


def determine_tier(labels_str: str) -> tuple:
    labels = [lbl.strip().lower() for lbl in labels_str.split(",")]
    for label in ["level:critical", "level:advanced"]:
        if label in labels:
            return LABEL_TIER_MAP[label]
    return ("🔥 Advanced-Level", "highly complex")


def validate_pr_size(pr: dict) -> None:
    """
    Validates if the PR is substantial enough to warrant a shoutout.
    - level:critical bypasses the check (critical bugs can be 1-line fixes).
    - level:advanced requires at least 40 lines changed.
    """
    labels = [lbl.strip().lower() for lbl in pr["labels"].split(",")]
    try:
        lines_changed = int(pr["lines_changed"])
    except ValueError:
        lines_changed = 0

    if "level:critical" in labels:
        print("⚡ PR is level:critical. Bypassing size check.")
        return

    if lines_changed < 40:
        print(f"🛑 REJECTED: PR only changed {lines_changed} lines.")
        print("   Advanced shoutouts require at least 40 lines of code changes.")
        print("   Exiting gracefully without triggering Make.com webhook or consuming AI credits.")
        sys.exit(0)
    
    print(f"✅ PR Size Validation Passed. Lines changed: {lines_changed} (Threshold: 40)")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Generate post with Gemini AI (Dynamic content)
# ─────────────────────────────────────────────────────────────────────────────
def generate_post_with_gemini(pr: dict, tier_display: str, tier_desc: str) -> str:
    """
    Calls Gemini 2.0 Flash to produce a unique, human-sounding LinkedIn post.
    High temperature = different text on every PR merge.
    Falls back to static template if API unavailable.
    """
    gemini_api_key = get_env_or_exit("GEMINI_API_KEY")

    system_prompt = (
        f"You are the social media voice of '{PROJECT_NAME}', {PROJECT_TAGLINE}. "
        "Write an authentic, enthusiastic LinkedIn post to celebrate a contributor. "
        "Keep it professional but warm. Use emojis appropriately. "
        "The post MUST feel human-written — never generic or AI-sounding. "
        "Never start with 'I am' or 'We are'. Be creative with the opening line each time. "
        "The post should be 150-250 words. Do NOT include hashtags — they will be added separately."
    )

    user_prompt = (
        f"Write a LinkedIn shoutout post celebrating this open-source contribution:\n\n"
        f"Contributor GitHub Username: @{pr['author']}\n"
        f"PR Title: {pr['title']}\n"
        f"PR Number: #{pr['number']}\n"
        f"Tier: {tier_display} ({tier_desc} contribution)\n"
        f"PR Link: {pr['url']}\n"
        f"Project: {PROJECT_NAME} — {PROJECT_TAGLINE}\n"
        f"PR Description: {pr['body'] if pr['body'] else 'Not provided'}\n\n"
        f"Requirements:\n"
        f"- Celebrate @{pr['author']} personally\n"
        f"- Explain what this PR does in simple terms\n"
        f"- Mention the '{tier_display}' difficulty tackled\n"
        f"- Invite other developers to contribute to SahiDawa\n"
        f"- End with a call-to-action to the PR or repo\n"
        f"- Tone: warm, inspiring, community-focused\n"
        f"- Do NOT mention any monetary reward"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={gemini_api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 400},
    }

    try:
        print("🤖 Calling Gemini AI to generate post...")
        resp = requests.post(url, headers={"Content-Type": "application/json"},
                             json=payload, timeout=30)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        print("✅ Gemini post generated successfully.")
        return text
    except Exception as exc:
        print(f"⚠️  Gemini AI failed ({exc}). Using static fallback.")
        return _static_fallback(pr, tier_display)


def _static_fallback(pr: dict, tier_display: str) -> str:
    return (
        f"🌟 Celebrating an incredible contribution to {PROJECT_NAME}!\n\n"
        f"Massive shoutout to @{pr['author']} for landing PR #{pr['number']} — "
        f'"{pr["title"]}" — a {tier_display} contribution to our codebase!\n\n'
        f"{PROJECT_NAME} is {PROJECT_TAGLINE}. With 200+ contributors from across the country, "
        "every merged PR brings us closer to making quality healthcare information accessible "
        "to every Indian citizen.\n\n"
        f"Thank you, @{pr['author']}, for your dedication and technical expertise!\n\n"
        f"👉 Check it out: {pr['url']}\n"
        f"🌐 Join us: {PROJECT_GITHUB_URL}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Assemble final post (Dynamic body + Static branding)
# ─────────────────────────────────────────────────────────────────────────────
def assemble_final_post(ai_content: str, pr: dict) -> str:
    clean = re.sub(r"\n{3,}", "\n\n", ai_content).strip()
    return (
        f"{clean}\n\n"
        f"─────────────────────\n"
        f"🔗 PR: {pr['url']}\n"
        f"⭐ Star & Contribute: {PROJECT_GITHUB_URL}\n\n"
        f"{PROJECT_HASHTAGS}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Send to Make.com Webhook (Make posts to LinkedIn Company Page)
# ─────────────────────────────────────────────────────────────────────────────
def send_to_make_webhook(post_text: str, pr: dict) -> None:
    """
    Sends a JSON payload to Make.com webhook.
    Make.com handles the LinkedIn Company Page posting — no Advertising API needed.

    Payload fields Make.com will receive:
      - post_text   : Full formatted LinkedIn post
      - pr_title    : PR title (for Make filters/conditions if needed)
      - pr_author   : Contributor GitHub username
      - pr_url      : Direct link to the PR
      - pr_number   : PR number
      - tier        : "level:advanced" or "level:critical"
    """
    webhook_url = get_env_or_exit("MAKE_WEBHOOK_URL")

    labels = pr["labels"].lower()
    tier = "level:critical" if "level:critical" in labels else "level:advanced"

    payload = {
        "post_text": post_text,
        "pr_title": pr["title"],
        "pr_author": pr["author"],
        "pr_url": pr["url"],
        "pr_number": pr["number"],
        "tier": tier,
    }

    print("📤 Sending post to Make.com webhook...")
    print(f"   Webhook: {webhook_url[:50]}...")
    resp = requests.post(
        webhook_url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )

    if resp.status_code == 200 and resp.text.strip().lower() == "accepted":
        print("✅ Make.com accepted the payload — LinkedIn post will be published.")
    elif resp.status_code == 200:
        print(f"✅ Make.com responded 200: {resp.text[:100]}")
    else:
        print(f"❌ Make.com webhook error: {resp.status_code} — {resp.text}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  SahiDawa LinkedIn Shoutout Bot (via Make.com)")
    print("=" * 60)

    pr = get_pr_metadata()
    print(f"\n📋 PR Details:")
    print(f"   Title  : {pr['title']}")
    print(f"   Author : @{pr['author']}")
    print(f"   Number : #{pr['number']}")
    print(f"   Labels : {pr['labels']}")
    print(f"   URL    : {pr['url']}")
    print(f"   Lines  : {pr['lines_changed']}\n")

    tier_display, tier_desc = determine_tier(pr["labels"])
    print(f"🏆 Tier: {tier_display}")

    # The Smart Gate Validation
    validate_pr_size(pr)

    ai_content = generate_post_with_gemini(pr, tier_display, tier_desc)
    final_post = assemble_final_post(ai_content, pr)

    print("\n" + "─" * 60)
    print("📝 FINAL POST PREVIEW:")
    print("─" * 60)
    print(final_post)
    print("─" * 60 + "\n")

    send_to_make_webhook(final_post, pr)
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
