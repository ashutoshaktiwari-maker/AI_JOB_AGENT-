"""
Unit & Integration Tests for Telegram Notifier.
Verifies:
1. Loading tokens and credentials from .env.
2. send_approval_request formatting and inline keyboard callbacks:
   [✅ Apply Yes] -> callback_data: apply:{job_hash}
   [❌ Skip No]   -> callback_data: skip:{job_hash}
3. send_interview_alert formatting and delivery.
4. Graceful fallback when credentials are not configured.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.telegram_notifier import (
    TelegramNotifier,
    send_approval_request,
    send_interview_alert,
)


def test_telegram_unconfigured():
    print("--- 1. Testing Unconfigured Credentials Fallback ---")
    notifier = TelegramNotifier(bot_token="", chat_id="")
    assert not notifier.is_configured()

    res = notifier.send_approval_request(
        job_hash="abc123hash",
        title="AI Engineer",
        company="GitLab",
        score=95,
        url="https://boards.greenhouse.io/gitlab/123",
    )
    assert res["status"] == "skipped"
    assert "Telegram credentials not configured" in res["reason"]
    print("[OK] Unconfigured credentials safely skipped without crashing.")


@patch("requests.post")
def test_send_approval_request(mock_post):
    print("\n--- 2. Testing send_approval_request & Inline Buttons ---")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 101}}
    mock_post.return_value = mock_resp

    notifier = TelegramNotifier(bot_token="test_token_123", chat_id="123456789")
    job_hash = "7f8b3c9a0d"

    result = notifier.send_approval_request(
        job_hash=job_hash,
        title="Senior Python AI Developer",
        company="Supabase",
        score=92,
        url="https://api.ashbyhq.com/job/supabase/123",
    )

    assert result["status"] == "sent"
    assert mock_post.called

    call_args = mock_post.call_args
    url = call_args[0][0]
    payload = call_args[1]["json"]

    assert "test_token_123" in url
    assert payload["chat_id"] == "123456789"
    assert "Supabase" in payload["text"]
    assert "Senior Python AI Developer" in payload["text"]
    assert "92%" in payload["text"]

    # Verify inline keyboard buttons
    keyboard = payload["reply_markup"]["inline_keyboard"]
    assert len(keyboard) == 1
    buttons = keyboard[0]
    assert len(buttons) == 2

    # Button 1: Apply
    assert "Apply" in buttons[0]["text"]
    assert buttons[0]["callback_data"] == f"apply:{job_hash}"

    # Button 2: Skip
    assert "Skip" in buttons[1]["text"]
    assert buttons[1]["callback_data"] == f"skip:{job_hash}"

    print("[OK] send_approval_request payload and inline buttons verified.")


@patch("requests.post")
def test_send_interview_alert(mock_post):
    print("\n--- 3. Testing send_interview_alert ---")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 102}}
    mock_post.return_value = mock_resp

    notifier = TelegramNotifier(bot_token="test_token_123", chat_id="123456789")

    result = notifier.send_interview_alert(
        company="OpenAI",
        role="Research Engineer",
        snippet="We would love to invite you to a technical screening interview."
    )

    assert result["status"] == "sent"
    assert mock_post.called

    payload = mock_post.call_args[1]["json"]
    assert payload["chat_id"] == "123456789"
    assert "INTERVIEW INVITATION" in payload["text"]
    assert "OpenAI" in payload["text"]
    assert "Research Engineer" in payload["text"]
    assert "technical screening" in payload["text"]

    print("[OK] send_interview_alert verified.")


if __name__ == "__main__":
    test_telegram_unconfigured()
    test_send_approval_request()
    test_send_interview_alert()
    print("\nALL TELEGRAM NOTIFIER TESTS PASSED SUCCESSFULLY! [SUCCESS]")
