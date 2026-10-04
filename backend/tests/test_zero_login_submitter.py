"""
Unit & Integration Tests for ZeroLoginSubmitter.
Verifies:
1. ATS Platform detection for Greenhouse, Ashby, and Lever.
2. Headless form auto-filling for First Name, Last Name, Email, Phone, LinkedIn, GitHub.
3. Resume file attachment via set_input_files().
4. Cloudflare Turnstile / CAPTCHA detection triggering 'needs_manual_review'.
5. Clean submission returning 'submitted'.
"""

import sys
import tempfile
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.zero_login_submitter import (
    ZeroLoginSubmitter,
    submit_job_application,
)


def test_platform_detection():
    print("--- 1. Testing Platform Detection ---")
    assert ZeroLoginSubmitter.detect_platform("https://boards.greenhouse.io/gitlab/jobs/123") == "greenhouse"
    assert ZeroLoginSubmitter.detect_platform("https://job-boards.greenhouse.io/canonical/jobs/456") == "greenhouse"
    assert ZeroLoginSubmitter.detect_platform("https://jobs.ashbyhq.com/supabase/789") == "ashby"
    assert ZeroLoginSubmitter.detect_platform("https://jobs.lever.co/palantir/abc") == "lever"
    print("[OK] Platform detection verified for Greenhouse, Ashby, and Lever.")


def test_headless_form_filling_and_submit():
    print("\n--- 2. Testing Headless Auto-Fill, Resume Attachment & Submission ---")

    # Create temporary resume file
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"Mock Tailored Resume Content for Senior AI Engineer")
        temp_resume_path = f.name

    # Create local mock HTML job application form simulating Greenhouse / Ashby
    mock_form_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Job Application Form</title></head>
    <body>
        <form id="application_form" action="#" method="POST">
            <input type="text" id="first_name" name="first_name" placeholder="First Name" />
            <input type="text" id="last_name" name="last_name" placeholder="Last Name" />
            <input type="email" id="email" name="email" placeholder="Email" />
            <input type="tel" id="phone" name="phone" placeholder="Phone" />
            <input type="text" name="linkedin" placeholder="LinkedIn URL" />
            <input type="text" name="github" placeholder="GitHub URL" />
            <input type="file" id="resume_file" name="resume" />
            <button type="submit" id="submit_app">Submit Application</button>
        </form>
    </body>
    </html>
    """

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(mock_form_html)
        temp_html_path = f.name

    file_url = Path(temp_html_path).as_uri()

    candidate_profile = {
        "name": "Ashutosh Tiwari",
        "email": "ashutosh.aktiwari@gmail.com",
        "phone": "+91 9876543210",
        "linkedin": "https://linkedin.com/in/ashutosh-tiwari",
        "github": "https://github.com/ashutoshaktiwari-maker",
    }

    result = ZeroLoginSubmitter.submit_application(
        url=file_url,
        resume_path=temp_resume_path,
        profile_data=candidate_profile,
        headless=True,
    )

    print("Submission Result:", result)
    assert result["status"] == "submitted"
    assert result["resume_attached"] is True
    assert "first_name" in result["fields_filled"]
    assert "last_name" in result["fields_filled"]
    assert "email" in result["fields_filled"]
    assert "phone" in result["fields_filled"]
    assert "linkedin" in result["fields_filled"]
    assert "github" in result["fields_filled"]

    # Cleanup temp files
    try:
        Path(temp_resume_path).unlink(missing_ok=True)
        Path(temp_html_path).unlink(missing_ok=True)
    except Exception:
        pass

    print("[OK] Headless form population, file upload, and submit verified.")


def test_turnstile_captcha_detection():
    print("\n--- 3. Testing Cloudflare Turnstile & CAPTCHA Pause Detection ---")

    # Mock form with Cloudflare Turnstile widget
    mock_turnstile_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Secured Job Application</title></head>
    <body>
        <form id="application_form">
            <input type="text" id="first_name" name="first_name" />
            <input type="text" id="last_name" name="last_name" />
            <input type="email" id="email" name="email" />
            <div class="cf-turnstile" data-turnstile-sitekey="0x4AAAAAAABBBCCC">Cloudflare Challenge</div>
            <button type="submit" id="submit_app">Submit</button>
        </form>
    </body>
    </html>
    """

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(mock_turnstile_html)
        temp_html_path = f.name

    file_url = Path(temp_html_path).as_uri()

    result = ZeroLoginSubmitter.submit_application(
        url=file_url,
        headless=True,
    )

    print("Turnstile Detection Result:", result)
    assert result["status"] == "needs_manual_review"
    assert "Challenge detected" in result["reason"] or "Turnstile" in result["reason"]

    try:
        Path(temp_html_path).unlink(missing_ok=True)
    except Exception:
        pass

    print("[OK] Turnstile challenge detection correctly flagged 'needs_manual_review'.")


if __name__ == "__main__":
    test_platform_detection()
    test_headless_form_filling_and_submit()
    test_turnstile_captcha_detection()
    print("\nALL ZERO-LOGIN SUBMITTER TESTS PASSED SUCCESSFULLY! [SUCCESS]")
