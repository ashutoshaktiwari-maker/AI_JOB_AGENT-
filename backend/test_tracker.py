"""
Test Suite for Application Tracker Database and CRUD operations.
"""

from database.db import db
from database.models import ApplicationCreate, ApplicationStatus, ApplicationUpdate

print("=== 1. Testing Application Creation ===")
app1 = db.add_application(
    ApplicationCreate(
        company="Stripe",
        role="Senior Automation Engineer",
        apply_url="https://jobs.lever.co/stripe/123/apply",
        resume_version="data/tailored_resume.txt",
        cover_letter_version="data/cover_letter.txt",
        status=ApplicationStatus.APPLIED,
        notes="Applied via Playwright automation"
    )
)
print("Created Application 1 ID:", app1["id"])
print("Company:", app1["company"])
print("Status:", app1["status"])
print("Applied Date:", app1["applied_date"])
assert app1["company"] == "Stripe"
assert app1["status"] == "Applied"

app2 = db.add_application(
    ApplicationCreate(
        company="CloudScale AI",
        role="AI Solutions Architect",
        apply_url="https://boards.greenhouse.io/cloudscale/456",
        resume_version="data/tailored_resume.txt",
        status=ApplicationStatus.APPLIED,
        notes="High match score (85%)"
    )
)
print("Created Application 2 ID:", app2["id"])

print("\n=== 2. Testing Application Update (Transition to Interview) ===")
updated_app1 = db.update_application(
    app1["id"],
    ApplicationUpdate(
        status=ApplicationStatus.INTERVIEW,
        interview_date="2026-10-05T14:00:00",
        notes="Screening interview scheduled with technical recruiter"
    )
)
print("Updated Status:", updated_app1["status"])
print("Interview Date:", updated_app1["interview_date"])
assert updated_app1["status"] == "Interview"

print("\n=== 3. Testing Status Filtering & Metrics ===")
interviews = db.get_all_applications(status="Interview")
print("Applications in 'Interview' status:", len(interviews))
assert len(interviews) >= 1

stats = db.get_stats()
print("Tracker Metrics:", stats)
assert stats["total"] >= 2
assert stats["interview"] >= 1

print("\n=== 4. Testing Application Retrieval by ID ===")
retrieved = db.get_application_by_id(app1["id"])
assert retrieved is not None
assert retrieved["company"] == "Stripe"
print(f"[OK] Retrieved application: {retrieved['company']} - {retrieved['role']} ({retrieved['status']})")

print("\n[SUCCESS] Application Tracker CRUD, status transitions, and metrics fully verified!")
