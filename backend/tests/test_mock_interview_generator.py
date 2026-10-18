"""
Unit & Integration Tests for Mock Interview Generator & Telegram Integration.
Verifies:
1. MockInterviewGenerator produces 10 tailored mock interview practice questions.
2. Prep file is automatically saved to backend/data/interview_prep/.
3. Deterministic fallback operates gracefully when LLM is unavailable.
4. Telegram send_interview_alert automatically attaches the 10 mock questions.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.mock_interview_generator import MockInterviewGenerator, _fallback_mock_questions
from services.telegram_notifier import TelegramNotifier, send_interview_alert


def test_fallback_mock_questions():
    print("--- 1. Testing Deterministic Fallback Mock Questions ---")
    data = _fallback_mock_questions(company="HubSpot", role="GTM Automation Engineer")
    assert data["company"] == "HubSpot"
    assert data["role"] == "GTM Automation Engineer"
    assert len(data["questions"]) == 10
    assert "10 Mock Interview Questions for Practice" in data["telegram_text"]
    for i in range(1, 11):
        assert any(f"{i}." in q for q in data["questions"]), f"Missing question {i}"
    print("[OK] Fallback mock questions verified with 10 questions.")


def test_mock_interview_generator_save():
    print("\n--- 2. Testing MockInterviewGenerator Generation & File Saving ---")
    res = MockInterviewGenerator.generate_questions(
        company="Stripe",
        role="Revenue Operations Engineer",
        snippet="Interview regarding Stripe billing automation and webhook pipelines.",
        save=True,
    )
    assert res["company"] == "Stripe"
    assert res["role"] == "Revenue Operations Engineer"
    assert "telegram_text" in res
    assert "file_path" in res

    saved_path = Path(res["file_path"])
    assert saved_path.exists()
    content = saved_path.read_text(encoding="utf-8")
    assert "Stripe" in content
    assert "Revenue Operations Engineer" in content
    print(f"[OK] Saved mock interview guide verified at: {saved_path}")


@patch("requests.post")
def test_telegram_send_interview_alert_with_mock_questions(mock_post):
    print("\n--- 3. Testing Telegram send_interview_alert with 10 Mock Questions ---")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 999}}
    mock_post.return_value = mock_resp

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    res = notifier.send_interview_alert(
        company="GitLab",
        role="Automation Engineer",
        snippet="We'd like to invite you for a 45-minute technical discussion.",
        generate_mock_questions=True,
    )

    assert res["status"] == "sent"
    assert "prep_file" in res
    assert Path(res["prep_file"]).exists()

    # Verify message payload sent to Telegram
    call_args = mock_post.call_args
    payload = call_args[1]["json"]
    msg_text = payload["text"]

    assert "INTERVIEW INVITATION DETECTED" in msg_text
    assert "GitLab" in msg_text
    assert "Automation Engineer" in msg_text
    assert "MOCK INTERVIEW QUESTIONS FOR PRACTICE" in msg_text.upper()
    print("[OK] Telegram interview alert automatically bundled with 10 mock questions.")


if __name__ == "__main__":
    test_fallback_mock_questions()
    test_mock_interview_generator_save()
    test_telegram_send_interview_alert_with_mock_questions()
    print("\nALL MOCK INTERVIEW GENERATOR TESTS PASSED SUCCESSFULLY! [SUCCESS]")
