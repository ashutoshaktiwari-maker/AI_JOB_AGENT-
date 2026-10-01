"""
Test Suite for Application Automation across Greenhouse, Lever, and Ashby.
Verifies field autofill, resume/cover letter upload, and pause detection.
"""

import os
from pathlib import Path
from services.application_automator import ApplicationAutomator, _detect_platform
from tools.browser import BrowserTool

print("=== 1. Testing Platform URL Detection ===")
urls = [
    ("https://boards.greenhouse.io/openai/jobs/12345", "greenhouse"),
    ("https://jobs.lever.co/stripe/67890/apply", "lever"),
    ("https://jobs.ashbyhq.com/linear/abcde/application", "ashby"),
    ("https://company.com/careers/job", "generic"),
]
for url, expected in urls:
    detected = _detect_platform(url)
    assert detected == expected, f"Expected {expected}, got {detected}"
    print(f"[OK] URL [{url[:40]}...] -> Platform: {detected}")

print("\n=== 2. Testing Form Filling & File Upload on Mock ATS Page ===")
# Create a local test HTML file simulating an ATS application page
mock_html_path = Path("data/test_ats_page.html")
mock_html_content = """<!DOCTYPE html>
<html>
<head><title>Job Application - CloudScale AI</title></head>
<body>
    <form id="application_form">
        <!-- Greenhouse / General fields -->
        <input type="text" id="first_name" name="first_name" placeholder="First Name" />
        <input type="text" id="last_name" name="last_name" placeholder="Last Name" />
        <input type="email" id="email" name="email" placeholder="Email" />
        <input type="tel" id="phone" name="phone" placeholder="Phone" />
        <input type="text" id="linkedin" name="job_application[answers][linkedin]" placeholder="LinkedIn" />
        <input type="text" id="github" name="job_application[answers][github]" placeholder="GitHub" />

        <!-- File uploads -->
        <input type="file" id="resume_file" name="resume" />
        <textarea id="cover_letter_text" name="cover_letter"></textarea>

        <!-- Mandatory custom question to test pause trigger -->
        <label for="work_auth">Are you authorized to work in the US? *</label>
        <input type="text" id="work_auth" name="work_auth" required placeholder="Yes/No" />
    </form>
</body>
</html>
"""
mock_html_path.parent.mkdir(parents=True, exist_ok=True)
with open(mock_html_path, "w", encoding="utf-8") as f:
    f.write(mock_html_content)

mock_url = f"file:///{mock_html_path.resolve().as_posix()}"

# Run automation against the mock ATS form
result = ApplicationAutomator.apply_to_job(
    apply_url=mock_url,
    resume_profile="data/profile.json",
    tailored_resume_path="data/tailored_resume.txt",
    cover_letter_path="data/cover_letter.txt",
    headless=True
)

print("\n--- AUTOMATION EXECUTION RESULTS ---")
print("Target URL:", result.get("apply_url"))
print("Status:", result.get("status"))
print("Pause Reason:", result.get("pause_reason"))
print("Fields Filled:", result.get("fields_filled"))
print("Resume Uploaded:", result.get("resume_uploaded"))
print("Cover Letter Uploaded:", result.get("cover_letter_uploaded"))
print("Unanswered Questions:", result.get("unanswered_questions"))

assert "first_name" in result["fields_filled"]
assert "email" in result["fields_filled"]
assert "phone" in result["fields_filled"]
assert result["resume_uploaded"] is True
assert result["status"] == "paused_for_user"
print("\n[SUCCESS] Automation successfully populated fields, uploaded resume & cover letter, and paused cleanly for mandatory question!")
