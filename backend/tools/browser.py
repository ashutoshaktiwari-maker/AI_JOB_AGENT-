"""
Browser Automation Tool powered by Playwright.

Manages browser instances, page navigation, form interactions,
file uploads, and detection of human-in-the-loop pause triggers
(CAPTCHA, OTP, and mandatory custom questions).
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

logger = logging.getLogger(__name__)


class BrowserTool:
    """Manages browser automation sessions with human-pause detection."""

    CAPTCHA_SELECTORS = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        "iframe[src*='turnstile']",
        "iframe[src*='arkoselabs']",
        "iframe[src*='challenge']",
        ".g-recaptcha",
        ".h-captcha",
        "#cf-challenge",
        "[data-sitekey]",
    ]

    OTP_SELECTORS = [
        "input[autocomplete='one-time-code']",
        "input[name*='otp']",
        "input[id*='otp']",
        "input[name*='verification_code']",
        "input[id*='verification_code']",
        "input[placeholder*='verification code' i]",
        "input[placeholder*='security code' i]",
    ]

    def __init__(self, headless: bool = False, timeout_ms: int = 30000):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def start(self) -> Page:
        """Launches Chromium browser and returns initial Page."""
        if not self._playwright:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context(
                viewport=None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.timeout_ms)
        return self._page

    def stop(self) -> None:
        """Safely terminates browser resources."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.debug("Browser cleanup notice: %s", e)
        finally:
            self._context = None
            self._browser = None
            self._playwright = None
            self._page = None

    def navigate(self, url: str) -> bool:
        """Navigates to URL and waits for DOM content to load."""
        if not self._page:
            self.start()
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            self._page.wait_for_timeout(2000)
            return True
        except Exception as e:
            logger.error("Failed to navigate to %s: %s", url, e)
            return False

    def check_for_captcha(self) -> Tuple[bool, str]:
        """Detects presence of CAPTCHA challenges."""
        if not self._page:
            return False, ""
        for selector in self.CAPTCHA_SELECTORS:
            try:
                locator = self._page.locator(selector).first
                if locator.count() > 0 and locator.is_visible():
                    return True, f"CAPTCHA challenge detected ({selector})"
            except Exception:
                continue
        return False, ""

    def check_for_otp(self) -> Tuple[bool, str]:
        """Detects presence of OTP or two-factor verification prompts."""
        if not self._page:
            return False, ""
        for selector in self.OTP_SELECTORS:
            try:
                locator = self._page.locator(selector).first
                if locator.count() > 0 and locator.is_visible():
                    return True, f"OTP / 2FA field detected ({selector})"
            except Exception:
                continue
        return False, ""

    def fill_first_match(self, selectors: List[str], value: str) -> bool:
        """Fills the first matching input element found on the page."""
        if not self._page or not value:
            return False
        for sel in selectors:
            try:
                elem = self._page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    elem.scroll_into_view_if_needed(timeout=2000)
                    elem.fill(value)
                    return True
            except Exception:
                continue
        return False

    def upload_file_first_match(self, selectors: List[str], file_path: str) -> bool:
        """Uploads a local file into the first matching file input."""
        if not self._page or not file_path or not os.path.exists(file_path):
            return False
        for sel in selectors:
            try:
                elem = self._page.locator(sel).first
                if elem.count() > 0:
                    elem.set_input_files(file_path)
                    return True
            except Exception:
                continue
        return False

    def check_unanswered_required_questions(self, common_filled_selectors: List[str]) -> List[str]:
        """Identifies mandatory custom questions that were not auto-filled."""
        unanswered = []
        if not self._page:
            return unanswered

        try:
            # Query all required inputs, selects, and textareas
            elements = self._page.query_selector_all("input[required], select[required], textarea[required], [aria-required='true']")
            for el in elements:
                try:
                    val = el.evaluate("(e) => (e.value || '').trim()")
                    if not val:
                        # Extract label or question text
                        label = el.evaluate("""
                            (e) => {
                                const id = e.id;
                                if (id) {
                                    const lbl = document.querySelector(`label[for="${id}"]`);
                                    if (lbl) return lbl.innerText.trim();
                                }
                                const parentLbl = e.closest('label') || e.closest('.field') || e.closest('.application-question');
                                return parentLbl ? parentLbl.innerText.trim() : (e.placeholder || e.name || 'Custom Field');
                            }
                        """)
                        if label and label not in unanswered:
                            unanswered.append(label.split("\n")[0].strip())
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Error checking required fields: %s", e)

        return unanswered[:5]  # Return top unanswered questions
