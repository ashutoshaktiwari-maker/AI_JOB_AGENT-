"""
Telegram Notification Service for AI Job Agent.

Handles:
1. Loading TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env.
2. Sending job approval requests with inline interactive buttons:
   [✅ Apply Yes] -> callback_data: apply:{job_hash}
   [❌ Skip No]   -> callback_data: skip:{job_hash}
3. Sending interview and screening invitation alerts to the candidate.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from backend/.env or root .env
def _load_env() -> None:
    backend_env = Path(__file__).resolve().parent.parent / ".env"
    root_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
    elif root_env.exists():
        load_dotenv(root_env)
    else:
        load_dotenv()

_load_env()


class TelegramNotifier:
    """Service for interacting with candidate via Telegram Bot API."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        _load_env()
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()

    def is_configured(self) -> bool:
        """Returns True if both bot token and chat ID are configured."""
        return bool(self.bot_token and self.chat_id)

    def _send_message(
        self,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "Markdown",
    ) -> Dict[str, Any]:
        """
        Sends message to candidate via Telegram Bot HTTP API.
        """
        if not self.is_configured():
            logger.warning(
                "Telegram credentials missing. Ensure TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID are set in .env."
            )
            return {
                "status": "skipped",
                "reason": "Telegram credentials not configured in .env",
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                logger.info("Telegram message delivered successfully.")
                return {"status": "sent", "result": data}
            else:
                logger.error(
                    "Telegram API error (%d): %s",
                    resp.status_code,
                    resp.text,
                )
                return {
                    "status": "failed",
                    "status_code": resp.status_code,
                    "error": resp.text,
                }
        except Exception as e:
            logger.error("Failed sending Telegram message: %s", e)
            return {"status": "error", "error": str(e)}

    def send_approval_request(
        self,
        job_hash: str,
        title: str,
        company: str,
        score: int | float,
        url: str,
    ) -> Dict[str, Any]:
        """
        Sends a Markdown notification with job details and inline action buttons:
        [✅ Apply Yes] -> callback_data: apply:{job_hash}
        [❌ Skip No]   -> callback_data: skip:{job_hash}
        """
        text = (
            f"🎯 *New Job Opportunity Match* ({score}% Fit)\n\n"
            f"🏢 *Company:* {company}\n"
            f"💼 *Role:* {title}\n"
            f"📊 *Match Score:* {score}%\n"
            f"🔗 [View Job Posting]({url})\n\n"
            f"Would you like the AI Agent to apply for this role?"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Apply Yes",
                        "callback_data": f"apply:{job_hash}",
                    },
                    {
                        "text": "❌ Skip No",
                        "callback_data": f"skip:{job_hash}",
                    },
                ]
            ]
        }

        return self._send_message(text=text, reply_markup=reply_markup)

    def send_interview_alert(
        self,
        company: str,
        role: str,
        snippet: str,
    ) -> Dict[str, Any]:
        """
        Sends an alert to Telegram that an interview or screening invite was discovered.
        """
        clean_snippet = snippet.strip()[:400]
        text = (
            f"🚨 *INTERVIEW INVITATION DETECTED!*\n\n"
            f"🏢 *Company:* {company}\n"
            f"💼 *Role:* {role}\n\n"
            f"📝 *Details:*\n"
            f"_{clean_snippet}_\n\n"
            f"⚡ Immediate candidate action recommended!"
        )

        return self._send_message(text=text)


# Standalone function helpers matching the exact requirement signatures
def send_approval_request(
    job_hash: str,
    title: str,
    company: str,
    score: int | float,
    url: str,
) -> Dict[str, Any]:
    """
    Sends a Markdown message with job details and inline action buttons:
    [✅ Apply Yes] -> callback_data: apply:{job_hash}
    [❌ Skip No]   -> callback_data: skip:{job_hash}
    """
    notifier = TelegramNotifier()
    return notifier.send_approval_request(
        job_hash=job_hash,
        title=title,
        company=company,
        score=score,
        url=url,
    )


def send_interview_alert(
    company: str,
    role: str,
    snippet: str,
) -> Dict[str, Any]:
    """
    Sends an alert to Telegram that an interview invite was discovered.
    """
    notifier = TelegramNotifier()
    return notifier.send_interview_alert(
        company=company,
        role=role,
        snippet=snippet,
    )
