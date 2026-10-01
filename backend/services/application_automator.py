"""
Application Automator Dispatcher.

Orchestrates automated job applications across Greenhouse, Lever, and Ashby
using Playwright. Enforces human-in-the-loop pauses for CAPTCHA, OTP, and
unanswered mandatory questions.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from tools.browser import BrowserTool
from services.greenhouse import GreenhouseAutomator
from services.lever import LeverAutomator
from services.ashby import AshbyAutomator

logger = logging.getLogger(__name__)


def _detect_platform(url: str) -> str:
    """Identifies the job board platform from URL."""
    domain = urlparse(url).netloc.lower()
    if "greenhouse.io" in domain or "gh_jid" in url:
        return "greenhouse"
    elif "lever.co" in domain:
        return "lever"
    elif "ashbyhq.com" in domain:
        return "ashby"
    return "generic"


class ApplicationAutomator:
    """Unified application automation controller for ATS job boards."""

    @classmethod
    def apply_to_job(
        cls,
        apply_url: str,
        resume_profile: Optional[Union[Dict[str, Any], str]] = None,
        tailored_resume_path: Optional[str] = None,
        cover_letter_path: Optional[str] = None,
        cover_letter_text: Optional[str] = None,
        headless: bool = False
    ) -> Dict[str, Any]:
        """
        Navigates to application URL, fills candidate details, uploads tailored resume
        and cover letter, and detects pause conditions.

        Args:
            apply_url: Job application web address.
            resume_profile: Profile dictionary or path to profile.json.
            tailored_resume_path: Path to tailored resume file.
            cover_letter_path: Path to cover letter file.
            cover_letter_text: Raw text of cover letter.
            headless: Whether to run browser without UI (defaults to False for review).

        Returns:
            Dict containing platform, status, fields_filled, pause_reason, unanswered_questions.
        """
        # 1. Load candidate profile
        candidate_data: Dict[str, Any] = {}
        if isinstance(resume_profile, dict):
            candidate_data = resume_profile
        elif isinstance(resume_profile, str) and os.path.exists(resume_profile):
            with open(resume_profile, "r", encoding="utf-8") as f:
                candidate_data = json.load(f)
        else:
            default_profile = Path("data/profile.json")
            if default_profile.exists():
                with open(default_profile, "r", encoding="utf-8") as f:
                    candidate_data = json.load(f)

        if not candidate_data:
            raise ValueError("No candidate profile available to populate application.")

        # 2. Resolve resume and cover letter asset paths
        resolved_resume = tailored_resume_path
        if not resolved_resume or not os.path.exists(resolved_resume):
            # Try default tailored resume or original resume
            if os.path.exists("data/tailored_resume.txt"):
                resolved_resume = "data/tailored_resume.txt"
            else:
                resolved_resume = candidate_data.get("resume_path", "")

        resolved_cover_path = cover_letter_path
        if not resolved_cover_path and os.path.exists("data/cover_letter.txt"):
            resolved_cover_path = "data/cover_letter.txt"

        resolved_cover_text = cover_letter_text
        if not resolved_cover_text and resolved_cover_path and os.path.exists(resolved_cover_path):
            try:
                with open(resolved_cover_path, "r", encoding="utf-8") as f:
                    resolved_cover_text = f.read()
            except Exception as e:
                logger.debug("Could not read cover letter file: %s", e)

        # 3. Detect target platform
        platform = _detect_platform(apply_url)
        browser = BrowserTool(headless=headless)

        try:
            browser.start()
            nav_success = browser.navigate(apply_url)
            if not nav_success:
                browser.stop()
                return {
                    "platform": platform.capitalize(),
                    "apply_url": apply_url,
                    "status": "failed",
                    "error": f"Failed to load application page at {apply_url}",
                    "fields_filled": [],
                    "resume_uploaded": False,
                    "cover_letter_uploaded": False,
                }

            # 4. Delegate to platform-specific automator
            if platform == "greenhouse":
                result = GreenhouseAutomator.apply(
                    browser=browser,
                    candidate_data=candidate_data,
                    resume_path=resolved_resume,
                    cover_letter_path=resolved_cover_path,
                    cover_letter_text=resolved_cover_text,
                )
            elif platform == "lever":
                result = LeverAutomator.apply(
                    browser=browser,
                    candidate_data=candidate_data,
                    resume_path=resolved_resume,
                    cover_letter_path=resolved_cover_path,
                    cover_letter_text=resolved_cover_text,
                )
            elif platform == "ashby":
                result = AshbyAutomator.apply(
                    browser=browser,
                    candidate_data=candidate_data,
                    resume_path=resolved_resume,
                    cover_letter_path=resolved_cover_path,
                    cover_letter_text=resolved_cover_text,
                )
            else:
                # Generic fallback: attempt standard greenhouse / lever selectors
                result = GreenhouseAutomator.apply(
                    browser=browser,
                    candidate_data=candidate_data,
                    resume_path=resolved_resume,
                    cover_letter_path=resolved_cover_path,
                    cover_letter_text=resolved_cover_text,
                )
                result["platform"] = "Generic / Custom"

            result["apply_url"] = apply_url
            return result

        finally:
            # Leave browser open briefly or stop
            if headless:
                browser.stop()
