"""
Zero-Login Headless Application Submitter powered by Playwright.

Navigates to open Greenhouse, Ashby, and Lever application URLs.
Auto-fills candidate profile fields:
- First Name, Last Name, Email, Phone, LinkedIn, GitHub
Attaches tailored resume via locator.set_input_files().
Detects CAPTCHA or Cloudflare Turnstile:
- If detected, pauses and returns status: "needs_manual_review"
- Otherwise, clicks submit and returns status: "submitted"
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from playwright.sync_api import Page, sync_playwright

logger = logging.getLogger(__name__)

# Turnstile, reCAPTCHA, and bot-challenge detection selectors
CAPTCHA_TURNSTILE_SELECTORS = [
    "iframe[src*='challenges.cloudflare.com']",
    "iframe[src*='turnstile']",
    ".cf-turnstile",
    "[data-turnstile-sitekey]",
    "#turnstile-wrapper",
    "iframe[src*='recaptcha']",
    "iframe[src*='google.com/recaptcha']",
    ".g-recaptcha",
    "[data-sitekey]",
    "iframe[src*='hcaptcha']",
    ".h-captcha",
    "#cf-challenge",
    "iframe[src*='challenge']",
    "iframe[src*='arkoselabs']",
]

# Standard candidate profile selectors across ATS platforms
FIELD_SELECTORS = {
    "first_name": [
        "#first_name",
        "input[name='first_name']",
        "input[name*='firstName' i]",
        "input[autocomplete='given-name']",
    ],
    "last_name": [
        "#last_name",
        "input[name='last_name']",
        "input[name*='lastName' i]",
        "input[autocomplete='family-name']",
    ],
    "full_name": [
        "input[name='name']",
        "#name",
        "input[placeholder*='Full name' i]",
        "input[placeholder*='Your name' i]",
        "input[autocomplete='name']",
    ],
    "email": [
        "#email",
        "input[name='email']",
        "input[type='email']",
        "input[autocomplete='email']",
    ],
    "phone": [
        "#phone",
        "input[name='phone']",
        "input[type='tel']",
        "input[autocomplete='tel']",
    ],
    "linkedin": [
        "input[name*='linkedin' i]",
        "input[id*='linkedin' i]",
        "input[name='urls[LinkedIn]']",
        "input[placeholder*='linkedin' i]",
    ],
    "github": [
        "input[name*='github' i]",
        "input[id*='github' i]",
        "input[name='urls[GitHub]']",
        "input[placeholder*='github' i]",
        "input[name*='website' i]",
        "input[name*='portfolio' i]",
    ],
}

RESUME_INPUT_SELECTORS = [
    "input#resume_file",
    "input[name='resume']",
    "#resume-upload-input",
    "input[data-qa='resume-upload']",
    "input[type='file'][name*='resume' i]",
    "input[type='file'][id*='resume' i]",
    "input[type='file']",
]

SUBMIT_BUTTON_SELECTORS = [
    "#submit_app",
    "#btn-submit",
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Submit Application')",
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "button:has-text('Apply')",
]


def resolve_profile_data(profile_path: Optional[str] = None) -> Dict[str, Any]:
    """Loads candidate data from profile_path or default locations."""
    candidates = [
        Path(profile_path) if profile_path else None,
        Path("backend/data/profile.json"),
        Path("data/profile.json"),
        Path(__file__).resolve().parent.parent / "data" / "profile.json",
    ]
    for p in candidates:
        if p and p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not parse profile at %s: %s", p, e)
    return {}


def resolve_resume_file(
    resume_path: Optional[str] = None,
    candidate_profile: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolves valid local path for the candidate's resume."""
    if resume_path and os.path.exists(resume_path):
        return resume_path

    candidates = [
        "backend/data/tailored/resume.pdf",
        "backend/data/tailored_resume.txt",
        "backend/data/resume.txt",
        "data/tailored_resume.txt",
        "data/resume.txt",
    ]
    if candidate_profile and candidate_profile.get("resume_path"):
        candidates.insert(0, candidate_profile["resume_path"])

    for c in candidates:
        if os.path.exists(c):
            return c
    return None


class ZeroLoginSubmitter:
    """Headless Playwright submitter for Greenhouse, Ashby, and Lever applications."""

    @staticmethod
    def detect_platform(url: str) -> str:
        """Identifies target ATS platform from URL."""
        netloc = urlparse(url).netloc.lower()
        if "greenhouse.io" in netloc or "gh_jid" in url:
            return "greenhouse"
        elif "ashbyhq.com" in netloc:
            return "ashby"
        elif "lever.co" in netloc:
            return "lever"
        return "generic"

    @staticmethod
    def check_for_captcha_or_turnstile(page: Page) -> tuple[bool, str]:
        """
        Inspects page DOM for Cloudflare Turnstile, reCAPTCHA, hCaptcha,
        or Arkose challenge elements.
        """
        for selector in CAPTCHA_TURNSTILE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible():
                    return True, f"Challenge detected ({selector})"
            except Exception:
                continue
        return False, ""

    @staticmethod
    def fill_field(page: Page, selectors: List[str], value: str) -> bool:
        """Fills the first matching input locator with given value."""
        if not value:
            return False
        for sel in selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    elem.scroll_into_view_if_needed(timeout=2000)
                    elem.fill(value)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def attach_resume_file(page: Page, file_path: str) -> bool:
        """Finds the resume input and attaches file via set_input_files()."""
        if not file_path or not os.path.exists(file_path):
            logger.warning("Resume file %s does not exist on disk.", file_path)
            return False

        for sel in RESUME_INPUT_SELECTORS:
            try:
                file_input = page.locator(sel).first
                if file_input.count() > 0:
                    file_input.set_input_files(file_path)
                    logger.info("Successfully attached resume (%s) to %s", file_path, sel)
                    return True
            except Exception as e:
                logger.debug("Failed setting input file on %s: %s", sel, e)
                continue
        return False

    @classmethod
    def submit_application(
        cls,
        url: str,
        resume_path: Optional[str] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        headless: bool = True,
        timeout_ms: int = 30000,
    ) -> Dict[str, Any]:
        """
        Executes zero-login headless application submission:
        1. Navigates to application URL.
        2. Detects CAPTCHA or Cloudflare Turnstile upfront.
        3. Auto-fills candidate profile fields.
        4. Attaches tailored resume file via set_input_files().
        5. Re-checks for CAPTCHA/Turnstile. If present, returns 'needs_manual_review'.
        6. Otherwise, clicks submit and returns 'submitted'.
        """
        # Resolve candidate data
        candidate = profile_data or resolve_profile_data()
        full_name = (candidate.get("name") or "").strip()
        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else first_name

        email_val = candidate.get("email", "").strip()
        phone_val = candidate.get("phone", "").strip()
        linkedin_val = candidate.get("linkedin", "").strip()
        github_val = candidate.get("github", "").strip()

        # Resolve resume asset path
        resolved_resume = resolve_resume_file(resume_path, candidate)
        platform = cls.detect_platform(url)

        fields_filled: List[str] = []
        resume_attached = False

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            try:
                logger.info("Navigating headless Playwright to: %s", url)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(2000)

                # 1. Upfront CAPTCHA / Turnstile check
                has_captcha, captcha_reason = cls.check_for_captcha_or_turnstile(page)
                if has_captcha:
                    logger.warning("CAPTCHA / Turnstile detected upfront on %s", url)
                    return {
                        "status": "needs_manual_review",
                        "reason": captcha_reason,
                        "platform": platform,
                        "url": url,
                        "fields_filled": [],
                        "resume_attached": False,
                    }

                # 2. Auto-fill candidate fields
                # First Name / Last Name
                if cls.fill_field(page, FIELD_SELECTORS["first_name"], first_name):
                    fields_filled.append("first_name")
                if cls.fill_field(page, FIELD_SELECTORS["last_name"], last_name):
                    fields_filled.append("last_name")

                # If platform only has single Full Name field
                if "first_name" not in fields_filled:
                    if cls.fill_field(page, FIELD_SELECTORS["full_name"], full_name):
                        fields_filled.append("name")

                # Email
                if cls.fill_field(page, FIELD_SELECTORS["email"], email_val):
                    fields_filled.append("email")

                # Phone
                if cls.fill_field(page, FIELD_SELECTORS["phone"], phone_val):
                    fields_filled.append("phone")

                # LinkedIn
                if linkedin_val and cls.fill_field(page, FIELD_SELECTORS["linkedin"], linkedin_val):
                    fields_filled.append("linkedin")

                # GitHub
                if github_val and cls.fill_field(page, FIELD_SELECTORS["github"], github_val):
                    fields_filled.append("github")

                # 3. Attach Tailored Resume
                if resolved_resume:
                    resume_attached = cls.attach_resume_file(page, resolved_resume)
                    if resume_attached:
                        fields_filled.append("resume")

                # Wait for any dynamic challenge scripts to trigger
                page.wait_for_timeout(1000)

                # 4. Check for CAPTCHA / Cloudflare Turnstile before submission
                has_captcha, captcha_reason = cls.check_for_captcha_or_turnstile(page)
                if has_captcha:
                    logger.warning("CAPTCHA / Turnstile challenge detected after filling: %s", captcha_reason)
                    return {
                        "status": "needs_manual_review",
                        "reason": captcha_reason,
                        "platform": platform,
                        "url": url,
                        "fields_filled": fields_filled,
                        "resume_attached": resume_attached,
                    }

                # 5. Click Submit Button
                submitted_click = False
                for btn_sel in SUBMIT_BUTTON_SELECTORS:
                    try:
                        submit_btn = page.locator(btn_sel).first
                        if submit_btn.count() > 0 and submit_btn.is_visible():
                            submit_btn.scroll_into_view_if_needed(timeout=2000)
                            submit_btn.click()
                            submitted_click = True
                            logger.info("Clicked submit button via selector: %s", btn_sel)
                            break
                    except Exception:
                        continue

                # Short wait to allow request processing or CAPTCHA popups
                page.wait_for_timeout(3000)

                # Post-submit verification check for CAPTCHA challenge
                has_captcha_post, post_reason = cls.check_for_captcha_or_turnstile(page)
                if has_captcha_post:
                    return {
                        "status": "needs_manual_review",
                        "reason": f"Post-submit challenge: {post_reason}",
                        "platform": platform,
                        "url": url,
                        "fields_filled": fields_filled,
                        "resume_attached": resume_attached,
                    }

                if submitted_click:
                    return {
                        "status": "submitted",
                        "platform": platform,
                        "url": url,
                        "fields_filled": fields_filled,
                        "resume_attached": resume_attached,
                    }
                else:
                    logger.warning("No submit button found for %s, marking for review.", url)
                    return {
                        "status": "needs_manual_review",
                        "reason": "Submit button not found or obscured",
                        "platform": platform,
                        "url": url,
                        "fields_filled": fields_filled,
                        "resume_attached": resume_attached,
                    }

            except Exception as exc:
                logger.error("Submission failed for %s: %s", url, exc)
                return {
                    "status": "needs_manual_review",
                    "reason": f"Execution exception: {str(exc)}",
                    "platform": platform,
                    "url": url,
                    "fields_filled": fields_filled,
                    "resume_attached": resume_attached,
                }
            finally:
                context.close()
                browser.close()


# Standalone function
def submit_job_application(
    url: str,
    resume_path: Optional[str] = None,
    profile_data: Optional[Dict[str, Any]] = None,
    headless: bool = True,
) -> Dict[str, Any]:
    """
    Submits a job application using headless Playwright.
    Auto-fills profile, attaches resume, checks for Turnstile/CAPTCHA,
    and returns 'needs_manual_review' or 'submitted'.
    """
    return ZeroLoginSubmitter.submit_application(
        url=url,
        resume_path=resume_path,
        profile_data=profile_data,
        headless=headless,
    )
