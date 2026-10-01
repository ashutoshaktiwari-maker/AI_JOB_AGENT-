"""
Lever Application Automator.

Fills Lever job application fields, uploads tailored resumes
and cover letters, and handles pause checkpoints for human verification.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from tools.browser import BrowserTool

logger = logging.getLogger(__name__)


class LeverAutomator:
    """Automates submission flow on Lever job boards (jobs.lever.co)."""

    @classmethod
    def apply(
        cls,
        browser: BrowserTool,
        candidate_data: Dict[str, Any],
        resume_path: str,
        cover_letter_path: Optional[str] = None,
        cover_letter_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes Lever form population and asset upload.
        """
        page = browser._page
        if not page:
            raise RuntimeError("Browser page not initialized.")

        filled_fields: List[str] = []

        # 1. Fill Name
        name = candidate_data.get("name", "").strip()
        if browser.fill_first_match(["input[name='name']", "#name"], name):
            filled_fields.append("name")

        # 2. Fill Email
        email = candidate_data.get("email", "").strip()
        if browser.fill_first_match(["input[name='email']", "#email"], email):
            filled_fields.append("email")

        # 3. Fill Phone
        phone = candidate_data.get("phone", "").strip()
        if browser.fill_first_match(["input[name='phone']", "#phone"], phone):
            filled_fields.append("phone")

        # 4. Fill Links (LinkedIn, GitHub)
        linkedin = candidate_data.get("linkedin", "").strip()
        if linkedin and browser.fill_first_match(["input[name='urls[LinkedIn]']", "input[name*='LinkedIn' i]"], linkedin):
            filled_fields.append("linkedin")

        github = candidate_data.get("github", "").strip()
        if github and browser.fill_first_match(["input[name='urls[GitHub]']", "input[name*='GitHub' i]"], github):
            filled_fields.append("github")

        # 5. Upload Resume
        resume_uploaded = False
        if resume_path and os.path.exists(resume_path):
            resume_selectors = [
                "#resume-upload-input",
                "input[name='resume']",
                "input[type='file']",
            ]
            resume_uploaded = browser.upload_file_first_match(resume_selectors, resume_path)
            if resume_uploaded:
                filled_fields.append("resume_file")

        # 6. Additional Info / Cover Letter
        cover_uploaded = False
        text_to_paste = cover_letter_text
        if not text_to_paste and cover_letter_path and os.path.exists(cover_letter_path):
            try:
                with open(cover_letter_path, "r", encoding="utf-8") as f:
                    text_to_paste = f.read()
            except Exception as e:
                logger.debug("Could not read cover letter file: %s", e)

        if text_to_paste:
            if browser.fill_first_match(["textarea[name='comments']", "textarea[name='additional-information']"], text_to_paste):
                cover_uploaded = True
                filled_fields.append("comments_cover_letter")

        # 7. Check for Pause Triggers (CAPTCHA, OTP, Mandatory Questions)
        has_captcha, captcha_msg = browser.check_for_captcha()
        if has_captcha:
            return {
                "platform": "Lever",
                "status": "paused_for_user",
                "pause_reason": captcha_msg,
                "fields_filled": filled_fields,
                "resume_uploaded": resume_uploaded,
                "cover_letter_uploaded": cover_uploaded,
                "unanswered_questions": [],
            }

        has_otp, otp_msg = browser.check_for_otp()
        if has_otp:
            return {
                "platform": "Lever",
                "status": "paused_for_user",
                "pause_reason": otp_msg,
                "fields_filled": filled_fields,
                "resume_uploaded": resume_uploaded,
                "cover_letter_uploaded": cover_uploaded,
                "unanswered_questions": [],
            }

        unanswered = browser.check_unanswered_required_questions(filled_fields)
        if unanswered:
            return {
                "platform": "Lever",
                "status": "paused_for_user",
                "pause_reason": f"Mandatory custom questions require attention: {', '.join(unanswered[:3])}",
                "fields_filled": filled_fields,
                "resume_uploaded": resume_uploaded,
                "cover_letter_uploaded": cover_uploaded,
                "unanswered_questions": unanswered,
            }

        return {
            "platform": "Lever",
            "status": "ready_to_submit",
            "pause_reason": None,
            "fields_filled": filled_fields,
            "resume_uploaded": resume_uploaded,
            "cover_letter_uploaded": cover_uploaded,
            "unanswered_questions": [],
        }
