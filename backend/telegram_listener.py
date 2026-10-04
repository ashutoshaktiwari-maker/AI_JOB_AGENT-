"""
Telegram Bot Listener for Candidate Approval & Interactive Job Actions.

Listens for user button presses from Telegram notifications:
- Callback query format: action:job_hash
- If action == 'skip':
    - Updates job status to 'rejected_by_user' in backend/data/jobs_memory.db.
    - Edits message to: "❌ Skipped."
- If action == 'apply':
    - Edits message to: "⏳ Launching headless Playwright automator..."
    - Retrieves cached tailored resume and cover letter paths from SQLite.
    - Calls ZeroLoginSubmitter.submit().
    - If success ('submitted'): Updates status to 'applied' and sends confirmation.
    - If CAPTCHA/paused ('needs_manual_review'): Updates status to 'needs_manual_review'
      and sends original URL for candidate completion.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from database.job_memory import get_job_by_hash, mark_job_status
from services.zero_login_submitter import ZeroLoginSubmitter
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logger = logging.getLogger(__name__)

# Load environment variables
def _load_env() -> None:
    backend_env = backend_dir / ".env"
    root_env = backend_dir.parent / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
    elif root_env.exists():
        load_dotenv(root_env)
    else:
        load_dotenv()

_load_env()


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles inline keyboard callbacks formatted as action:job_hash.
    Executes 'skip' or 'apply' workflows.
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = (query.data or "").strip()

    if ":" not in data:
        logger.warning("Unrecognized callback data format: %s", data)
        return

    action, job_hash = data.split(":", 1)
    action = action.strip().lower()
    job_hash = job_hash.strip()

    # 1. Action: SKIP
    if action == "skip":
        mark_job_status(job_hash, "rejected_by_user")
        await query.edit_message_text(text="❌ Skipped.")
        logger.info("Job %s updated to status 'rejected_by_user'.", job_hash)
        return

    # 2. Action: APPLY
    if action == "apply":
        await query.edit_message_text(text="⏳ Launching headless Playwright automator...")

        job = get_job_by_hash(job_hash)
        if not job:
            await query.edit_message_text(text="⚠️ Error: Job not found in local memory database.")
            logger.warning("Job hash %s not found in SQLite memory.", job_hash)
            return

        url = job.get("url", "")
        resume_path = job.get("tailored_resume_path")
        company = job.get("company", "Company")
        title = job.get("title", "Role")

        if not url:
            await query.edit_message_text(text="⚠️ Error: Missing application URL for this job.")
            return

        # Execute headless Playwright submitter in thread to avoid event loop conflicts
        try:
            result = await asyncio.to_thread(
                ZeroLoginSubmitter.submit,
                url=url,
                resume_path=resume_path,
                headless=True,
            )
        except Exception as exc:
            logger.error("Submission error for %s: %s", job_hash, exc)
            result = {"status": "needs_manual_review", "reason": str(exc)}

        status = result.get("status")

        # Success: Submitted
        if status == "submitted":
            mark_job_status(job_hash, "applied")
            confirmation_text = (
                f"✅ *Application Successfully Submitted!* 🎉\n\n"
                f"🏢 *Company:* {company}\n"
                f"💼 *Role:* {title}\n"
                f"🔗 [View Job Posting]({url})\n\n"
                f"Status updated in Tracker: *APPLIED*."
            )
            await query.edit_message_text(
                text=confirmation_text,
                parse_mode="Markdown",
            )
            logger.info("Job %s successfully submitted and marked as 'applied'.", job_hash)

        # CAPTCHA / Turnstile / Manual Review Paused
        else:
            mark_job_status(job_hash, "needs_manual_review")
            pause_reason = result.get("reason") or "Challenge or manual review required"
            review_text = (
                f"⚠️ *Manual Review Required*\n\n"
                f"🏢 *Company:* {company}\n"
                f"💼 *Role:* {title}\n"
                f"ℹ️ *Notice:* {pause_reason}\n\n"
                f"Please open and complete the application manually:\n"
                f"🔗 [Open Application Form]({url})"
            )
            await query.edit_message_text(
                text=review_text,
                parse_mode="Markdown",
            )
            logger.info("Job %s flagged for manual review: %s", job_hash, pause_reason)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcomes candidate and confirms listener status."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "👋 *AI Job Agent Connected!*\n\n"
            "I will notify you of high-matching roles and interview invitations here. "
            "Use inline buttons on job alerts to trigger instant headless applications or skip positions.",
            parse_mode="Markdown",
        )


def build_application(token: Optional[str] = None) -> Application:
    """
    Builds the python-telegram-bot Application instance with CallbackQueryHandler.
    """
    _load_env()
    bot_token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env.")

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    return app


def run_listener() -> None:
    """Starts the Telegram polling loop."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    app = build_application()
    logger.info("Telegram listener is active and waiting for button events...")
    app.run_polling()


if __name__ == "__main__":
    run_listener()
