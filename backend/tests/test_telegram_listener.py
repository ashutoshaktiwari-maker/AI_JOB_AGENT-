"""
Unit & Integration Tests for Telegram Listener.
Verifies:
1. ApplicationBuilder initialization with CallbackQueryHandler.
2. Callback query handling:
   - 'skip' action -> marks job 'rejected_by_user' and edits message to '❌ Skipped.'
   - 'apply' action -> launches submitter:
     - on 'submitted' -> marks job 'applied' and sends confirmation message.
     - on 'needs_manual_review' -> marks job 'needs_manual_review' and sends URL.
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from database.job_memory import (
    save_discovered_job,
    get_job_by_hash,
    update_job_assets,
    init_db,
)
from telegram_listener import (
    handle_callback_query,
    build_application,
)


def setup_module():
    init_db()


def test_build_application():
    print("--- 1. Testing ApplicationBuilder Initialization ---")
    app = build_application(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    assert app is not None
    # Verify CallbackQueryHandler is registered
    handlers = app.handlers[0]
    has_callback_handler = any(type(h).__name__ == "CallbackQueryHandler" for h in handlers)
    assert has_callback_handler, "CallbackQueryHandler must be registered in app."
    print("[OK] ApplicationBuilder successfully configured with CallbackQueryHandler.")


def test_handle_skip_action():
    print("\n--- 2. Testing Callback Query: action == 'skip' ---")
    job_url = f"https://job-boards.greenhouse.io/test/skip/{int(time.time()*1000)}"
    job_dict = {
        "company": "GitLab",
        "title": "Backend Go Engineer",
        "url": job_url,
        "location": "Remote",
        "description": "Golang distributed systems role.",
        "portal": "Greenhouse",
    }
    job_hash = save_discovered_job(job_dict, match_score=85)

    # Setup mock Update and Query
    mock_query = AsyncMock()
    mock_query.data = f"skip:{job_hash}"
    mock_query.answer = AsyncMock()
    mock_query.edit_message_text = AsyncMock()

    mock_update = MagicMock()
    mock_update.callback_query = mock_query

    mock_context = MagicMock()

    # Run async handler
    asyncio.run(handle_callback_query(mock_update, mock_context))

    # Verify query.answer and message edit
    mock_query.answer.assert_awaited_once()
    mock_query.edit_message_text.assert_awaited_once_with(text="❌ Skipped.")

    # Verify SQLite status updated to 'rejected_by_user'
    job_record = get_job_by_hash(job_hash)
    assert job_record is not None
    assert job_record["status"] == "rejected_by_user"
    print("[OK] Skip action properly marked 'rejected_by_user' in SQLite.")


@patch("telegram_listener.ZeroLoginSubmitter.submit")
def test_handle_apply_success(mock_submit):
    print("\n--- 3. Testing Callback Query: action == 'apply' (Success: Submitted) ---")
    mock_submit.return_value = {
        "status": "submitted",
        "url": "https://jobs.ashbyhq.com/supabase/ai-dev",
        "fields_filled": ["first_name", "last_name", "email", "resume"],
        "resume_attached": True,
    }

    job_url = f"https://jobs.ashbyhq.com/supabase/ai-dev/{int(time.time()*1000)}"
    job_dict = {
        "company": "Supabase",
        "title": "AI Cloud Architect",
        "url": job_url,
        "location": "Worldwide",
        "description": "Vector indexing & AI platform.",
        "portal": "Ashby",
    }
    job_hash = save_discovered_job(job_dict, match_score=94)
    update_job_assets(job_hash, "backend/data/tailored_resume.txt", "backend/data/cover_letter.txt")

    mock_query = AsyncMock()
    mock_query.data = f"apply:{job_hash}"
    mock_query.answer = AsyncMock()
    mock_query.edit_message_text = AsyncMock()

    mock_update = MagicMock()
    mock_update.callback_query = mock_query
    mock_context = MagicMock()

    asyncio.run(handle_callback_query(mock_update, mock_context))

    # Verify initial launch message and subsequent success edit
    assert mock_query.edit_message_text.call_count >= 2
    final_call = mock_query.edit_message_text.call_args_list[-1]
    final_text = final_call.kwargs.get("text") or final_call.args[0]

    assert "Application Successfully Submitted" in final_text
    assert "Supabase" in final_text
    assert "AI Cloud Architect" in final_text

    # Verify SQLite status updated to 'applied'
    job_record = get_job_by_hash(job_hash)
    assert job_record is not None
    assert job_record["status"] == "applied"
    assert job_record["applied_at"] is not None
    print("[OK] Apply action properly marked 'applied' in SQLite upon successful submission.")


@patch("telegram_listener.ZeroLoginSubmitter.submit")
def test_handle_apply_captcha_pause(mock_submit):
    print("\n--- 4. Testing Callback Query: action == 'apply' (Paused: Turnstile Challenge) ---")
    mock_submit.return_value = {
        "status": "needs_manual_review",
        "reason": "Cloudflare Turnstile challenge detected",
        "url": "https://jobs.lever.co/palantir/sec-eng",
        "fields_filled": ["first_name", "last_name", "email"],
        "resume_attached": True,
    }

    job_url = f"https://jobs.lever.co/palantir/sec-eng/{int(time.time()*1000)}"
    job_dict = {
        "company": "Palantir",
        "title": "Forward Deployed AI Engineer",
        "url": job_url,
        "location": "APAC Remote",
        "description": "Deploy LLM agents on Foundry.",
        "portal": "Lever",
    }
    job_hash = save_discovered_job(job_dict, match_score=91)

    mock_query = AsyncMock()
    mock_query.data = f"apply:{job_hash}"
    mock_query.answer = AsyncMock()
    mock_query.edit_message_text = AsyncMock()

    mock_update = MagicMock()
    mock_update.callback_query = mock_query
    mock_context = MagicMock()

    asyncio.run(handle_callback_query(mock_update, mock_context))

    # Verify final manual review notice containing URL
    final_call = mock_query.edit_message_text.call_args_list[-1]
    final_text = final_call.kwargs.get("text") or final_call.args[0]

    assert "Manual Review Required" in final_text
    assert "Palantir" in final_text
    assert job_url in final_text

    # Verify SQLite status updated to 'needs_manual_review'
    job_record = get_job_by_hash(job_hash)
    assert job_record is not None
    assert job_record["status"] == "needs_manual_review"
    print("[OK] Apply action properly marked 'needs_manual_review' and sent manual completion URL.")


if __name__ == "__main__":
    test_build_application()
    test_handle_skip_action()
    test_handle_apply_success()
    test_handle_apply_captcha_pause()
    print("\nALL TELEGRAM LISTENER TESTS PASSED SUCCESSFULLY! [SUCCESS]")
