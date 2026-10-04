"""
Unit & Integration Tests for GmailJobReader.
Verifies:
1. Google OAuth scopes (gmail.readonly & gmail.modify) and file resolution.
2. Search query construction: is:unread ("Python AI" OR "AI Agent" OR "remote" ...)
3. Content extraction: sender, subject, body, recruiter_email, apply_urls.
4. Interview detection: flags is_interview for screening, invitation, schedule a call.
5. Mark as READ logic to prevent duplicate alerts.
6. Mocked end-to-end scan_job_emails execution.
"""

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.gmail_job_reader import (
    GmailJobReader,
    scan_job_emails,
    SCOPES,
    resolve_oauth_paths,
)


def test_oauth_configuration():
    print("--- 1. Testing OAuth Scopes & Path Resolution ---")
    assert "https://www.googleapis.com/auth/gmail.readonly" in SCOPES
    assert "https://www.googleapis.com/auth/gmail.modify" in SCOPES

    creds_path, token_path = resolve_oauth_paths()
    assert creds_path.name == "credentials.json"
    assert token_path.name == "token.json"
    print("[OK] OAuth scopes and credential paths verified.")


def test_query_construction():
    print("\n--- 2. Testing Gmail Search Query Generation ---")
    kws = ["Python AI", "AI Agent", "remote"]
    q = GmailJobReader.build_search_query(kws)
    expected = 'is:unread ("Python AI" OR "AI Agent" OR "remote")'
    assert q == expected, f"Query mismatch: expected '{expected}', got '{q}'"

    q_empty = GmailJobReader.build_search_query([])
    assert q_empty == "is:unread"

    q_single = GmailJobReader.build_search_query(["LLM Engineer"])
    assert q_single == 'is:unread ("LLM Engineer")'
    print("[OK] Search query generation matches specification.")


def test_interview_detection():
    print("\n--- 3. Testing Interview & Screening Flag Detection ---")
    assert GmailJobReader.is_interview_email(
        subject="Interview Invitation: AI Engineer Next Steps",
        body="We would love to speak with you regarding the role."
    ) is True

    assert GmailJobReader.is_interview_email(
        subject="Application Update",
        body="Are you available for a 30-minute technical screening call?"
    ) is True

    assert GmailJobReader.is_interview_email(
        subject="Quick catch up",
        body="Let's schedule a call this Thursday at 2 PM."
    ) is True

    assert GmailJobReader.is_interview_email(
        subject="Invitation: Software Engineer Assessment",
        body="Please complete the coding test."
    ) is True

    assert GmailJobReader.is_interview_email(
        subject="Daily Job Alert: 10 New Python Positions",
        body="Here are remote jobs posted today in APAC."
    ) is False
    print("[OK] Interview detection logic fully verified.")


def test_recruiter_and_url_extraction():
    print("\n--- 4. Testing Recruiter Email & ATS URL Extraction ---")
    # Case A: Direct human recruiter sender
    email_a = GmailJobReader.detect_recruiter_email(
        sender="Sarah Miller <sarah.m@techcorp.io>",
        body="Hi Ashutosh, I'm reaching out about a Python AI opening."
    )
    assert email_a == "sarah.m@techcorp.io"

    # Case B: Automated notification bot with recruiter email in body
    body_b = """
    Notification from TalentPortal:
    A new role was matched. Please contact recruiter: emily.talent@openai.com.
    You can also apply at: https://boards.greenhouse.io/openai/jobs/998877
    """
    email_b = GmailJobReader.detect_recruiter_email(
        sender="notifications@talentportal.com",
        body=body_b
    )
    assert email_b == "emily.talent@openai.com"

    urls_b = GmailJobReader.extract_apply_urls(body_b)
    assert "https://boards.greenhouse.io/openai/jobs/998877" in urls_b
    print("[OK] Recruiter email and ATS URL extraction verified.")


def test_mocked_scan_job_emails():
    print("\n--- 5. Testing Mocked scan_job_emails Execution & Mark as READ ---")
    reader = GmailJobReader()

    # Create mock Gmail service
    mock_service = MagicMock()
    mock_messages_resource = MagicMock()
    mock_service.users().messages.return_value = mock_messages_resource

    # 1. Mock list call
    mock_messages_resource.list().execute.return_value = {
        "messages": [{"id": "msg_001"}, {"id": "msg_002"}]
    }

    # 2. Mock get call for msg_001 (Interview invite)
    body1_text = (
        "Hi Ashutosh, We'd like to invite you for an interview. "
        "Apply or review details at: https://jobs.lever.co/acme/123/apply. "
        "Contact: recruiter@acme.com"
    )
    body1_b64 = base64.urlsafe_b64encode(body1_text.encode("utf-8")).decode("utf-8")

    full_msg_1 = {
        "id": "msg_001",
        "payload": {
            "headers": [
                {"name": "From", "value": "recruiter@acme.com"},
                {"name": "Subject", "value": "Interview Invitation: Senior AI Lead"},
                {"name": "Date", "value": "Fri, 03 Oct 2026 12:00:00 GMT"},
            ],
            "body": {"data": body1_b64},
        },
    }

    # Mock get call for msg_002 (General job alert)
    body2_text = (
        "New Python AI job available at Stripe. "
        "Apply: https://stripe.com/jobs/456"
    )
    body2_b64 = base64.urlsafe_b64encode(body2_text.encode("utf-8")).decode("utf-8")

    full_msg_2 = {
        "id": "msg_002",
        "payload": {
            "headers": [
                {"name": "From", "value": "jobs@stripe.com"},
                {"name": "Subject", "value": "New Remote Role: Python AI Engineer"},
                {"name": "Date", "value": "Fri, 03 Oct 2026 13:00:00 GMT"},
            ],
            "body": {"data": body2_b64},
        },
    }

    def get_msg_side_effect(userId, id, format):
        mock_execute = MagicMock()
        if id == "msg_001":
            mock_execute.execute.return_value = full_msg_1
        else:
            mock_execute.execute.return_value = full_msg_2
        return mock_execute

    mock_messages_resource.get.side_effect = get_msg_side_effect

    # Inject mock service
    reader._service = mock_service

    # Execute scan
    results = reader.scan_job_emails(
        keywords=["Python AI", "AI Agent", "remote"],
        mark_read=True
    )

    assert len(results) == 2, f"Expected 2 results, got {len(results)}"

    # Verify msg_001
    item1 = results[0]
    assert item1["id"] == "msg_001"
    assert item1["sender"] == "recruiter@acme.com"
    assert item1["subject"] == "Interview Invitation: Senior AI Lead"
    assert item1["recruiter_email"] == "recruiter@acme.com"
    assert item1["is_interview"] is True
    assert "https://jobs.lever.co/acme/123/apply" in item1["apply_urls"]

    # Verify msg_002
    item2 = results[1]
    assert item2["id"] == "msg_002"
    assert item2["subject"] == "New Remote Role: Python AI Engineer"
    assert item2["is_interview"] is False
    assert "https://stripe.com/jobs/456" in item2["apply_urls"]

    # Verify mark as READ was called for both messages
    # Each call to modify should remove "UNREAD" label
    assert mock_messages_resource.modify.call_count == 2
    mock_messages_resource.modify.assert_any_call(
        userId="me",
        id="msg_001",
        body={"removeLabelIds": ["UNREAD"]},
    )
    mock_messages_resource.modify.assert_any_call(
        userId="me",
        id="msg_002",
        body={"removeLabelIds": ["UNREAD"]},
    )

    print("[OK] Mocked scan_job_emails and mark as READ verified.")


if __name__ == "__main__":
    test_oauth_configuration()
    test_query_construction()
    test_interview_detection()
    test_recruiter_and_url_extraction()
    test_mocked_scan_job_emails()
    print("\nALL GMAIL JOB READER TESTS PASSED SUCCESSFULLY! [SUCCESS]")
