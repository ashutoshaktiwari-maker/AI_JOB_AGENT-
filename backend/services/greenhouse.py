"""
Greenhouse Application Automator.

Fills Greenhouse job application fields, uploads tailored resumes
and cover letters, and handles pause checkpoints for human verification.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from tools.browser import BrowserTool

logger = logging.getLogger(__name__)


class GreenhouseAutomator:
    """Automates submission flow on Greenhouse job boards."""

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
        Executes Greenhouse form population and asset upload.
        """
        page = browser._page
        if not page:
            raise RuntimeError("Browser page not initialized.")

        filled_fields: List[str] = []

        # Split full name into first and last name
        full_name = candidate_data.get("name", "").strip()
        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else first_name

        # 1. Fill Name fields
        if browser.fill_first_match(["#first_name", "input[name='first_name']", "input[autocomplete='given-name']"], first_name):
            filled_fields.append("first_name")
        if browser.fill_first_match(["#last_name", "input[name='last_name']", "input[autocomplete='family-name']"], last_name):
            filled_fields.append("last_name")

        # 2. Fill Email
        email = candidate_data.get("email", "")
        if browser.fill_first_match(["#email", "input[name='email']", "input[type='email']"], email):
            filled_fields.append("email")

        # 3. Fill Phone
        phone = candidate_data.get("phone", "")
        if browser.fill_first_match(["#phone", "input[name='phone']", "input[type='tel']"], phone):
            filled_fields.append("phone")

        # 4. Fill Social / Portfolio URLs
        linkedin = candidate_data.get("linkedin", "")
        if linkedin and browser.fill_first_match(["input[name*='linkedin' i]", "input[id*='linkedin' i]"], linkedin):
            filled_fields.append("linkedin")

        github = candidate_data.get("github", "")
        if github and browser.fill_first_match(["input[name*='github' i]", "input[id*='github' i]", "input[name*='website' i]"], github):
            filled_fields.append("github")

        # 5. Upload Resume
        resume_uploaded = False
        if resume_path and os.path.exists(resume_path):
            resume_selectors = [
                "input#resume_file",
                "input[name='resume']",
                "input[data-qa='resume-upload']",
                "input[type='file'][name*='resume' i]",
                "input[type='file']",
            ]
            resume_uploaded = browser.upload_file_first_match(resume_selectors, resume_path)
            if resume_uploaded:
                filled_fields.append("resume_file")

        # 6. Upload Cover Letter or Fill Textarea
        cover_uploaded = False
        if cover_letter_text:
            if browser.fill_first_match(["textarea#cover_letter_text", "textarea[name*='cover_letter' i]"], cover_letter_text):
                cover_uploaded = True
                filled_fields.append("cover_letter_text")

        if not cover_uploaded and cover_letter_path and os.path.exists(cover_letter_path):
            cover_selectors = [
                "input#cover_letter_file",
                "input[name='cover_letter']",
                "input[data-qa='cover-letter-upload']",
                "input[type='file'][name*='cover' i]",
            ]
            cover_uploaded = browser.upload_file_first_match(cover_selectors, cover_letter_path)
            if cover_uploaded:
                filled_fields.append("cover_letter_file")

        # 7. Check for Pause Triggers (CAPTCHA, OTP, Mandatory Questions)
        has_captcha, captcha_msg = browser.check_for_captcha()
        if has_captcha:
            return {
                "platform": "Greenhouse",
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
                "platform": "Greenhouse",
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
                "platform": "Greenhouse",
                "status": "paused_for_user",
                "pause_reason": f"Mandatory custom questions require attention: {', '.join(unanswered[:3])}",
                "fields_filled": filled_fields,
                "resume_uploaded": resume_uploaded,
                "cover_letter_uploaded": cover_uploaded,
                "unanswered_questions": unanswered,
            }

        return {
            "platform": "Greenhouse",
            "status": "ready_to_submit",
            "pause_reason": None,
            "fields_filled": filled_fields,
            "resume_uploaded": resume_uploaded,
            "cover_letter_uploaded": cover_uploaded,
            "unanswered_questions": [],
        }
