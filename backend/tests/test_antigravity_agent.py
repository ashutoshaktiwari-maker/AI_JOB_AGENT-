"""
Unit and Integration Tests for backend/antigravity_agent.py.

Verifies:
1. Google Antigravity Agent initialization (Agent, LocalAgentConfig).
2. run_autonomous_cycle execution:
   - Job fetching via ZeroLoginJobFetcher with target keywords.
   - Deduplication against SQLite (is_job_saved).
   - Match scoring with analyze_match against profile.json.
   - Job saving in SQLite (save_discovered_job).
   - Tailored asset generation for score >= 65 to backend/data/tailored/{job_hash}/:
     * resume.txt
     * cover_letter.txt
   - Database update with asset paths (update_job_assets).
   - Telegram interactive approval dispatch (send_approval_request).
   - Low score (< 65) filtering: no asset generation, no approval request.
   - Gmail scanning and interview alert dispatch (send_interview_alert).
3. APScheduler configuration (2-hour recurring interval).
"""

import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from google.antigravity import Agent, LocalAgentConfig
from antigravity_agent import (
    DEFAULT_KEYWORDS,
    MIN_MATCH_THRESHOLD,
    autonomous_agent,
    build_scheduler,
    create_antigravity_agent,
    resolve_profile_path,
    resolve_tailored_dir,
    run_autonomous_cycle,
)
from database.job_memory import (
    generate_job_hash,
    get_job_by_hash,
    init_db,
    is_job_saved,
    save_discovered_job,
)


def setup_module():
    """Ensure database schema is ready before running tests."""
    init_db()


def test_google_antigravity_agent_initialization():
    """Verify that Google Antigravity Agent and LocalAgentConfig initialize properly."""
    print("--- 1. Testing Google Antigravity Agent Initialization ---")
    assert isinstance(autonomous_agent, Agent)
    agent = create_antigravity_agent()
    assert isinstance(agent, Agent)
    print("[OK] Google Antigravity Agent successfully initialized.")


def test_scheduler_configuration():
    """Verify that APScheduler is correctly configured for 2-hour intervals."""
    print("--- 2. Testing APScheduler Configuration ---")
    scheduler = build_scheduler(hours=2, blocking=False)
    assert scheduler is not None

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "autonomous_job_agent_cycle"
    # Verify trigger interval is 2 hours (7200 seconds)
    assert job.trigger.interval.total_seconds() == 7200
    print("[OK] APScheduler job registered with 2-hour interval.")


def test_run_autonomous_cycle_end_to_end():
    """Verify the full autonomous cycle logic with qualified and unqualified jobs, and emails."""
    print("--- 3. Testing Full Autonomous Cycle End-to-End ---")

    test_ts = int(time.time() * 1000)
    qualified_url = f"https://job-boards.greenhouse.io/gitlab/jobs/high-{test_ts}"
    unqualified_url = f"https://job-boards.greenhouse.io/gitlab/jobs/low-{test_ts}"
    already_saved_url = f"https://job-boards.greenhouse.io/gitlab/jobs/saved-{test_ts}"

    # Pre-save one job to verify deduplication
    save_discovered_job(
        {
            "company": "GitLab",
            "title": "Old Backend Engineer",
            "url": already_saved_url,
            "description": "Pre-existing job",
        },
        match_score=50,
    )
    assert is_job_saved(already_saved_url)

    mock_discovered_jobs = [
        # Job 1: High match (88%) -> Should generate assets, save to DB, alert Telegram
        {
            "id": f"job-1-{test_ts}",
            "title": "Lead Python AI Engineer",
            "company": "Supabase",
            "url": qualified_url,
            "location": "Remote, Global",
            "description": "Building LLM autonomous multi-agent pipelines with Python and FastAPI.",
            "portal": "Ashby (Supabase)",
        },
        # Job 2: Low match (42%) -> Should save to DB, but skip assets and Telegram alert
        {
            "id": f"job-2-{test_ts}",
            "title": "C++ Embedded Firmware Engineer",
            "company": "RoboCorp",
            "url": unqualified_url,
            "location": "Remote, India",
            "description": "Microcontroller firmware programming in pure C/C++.",
            "portal": "Greenhouse",
        },
        # Job 3: Already saved -> Should be skipped entirely
        {
            "id": f"job-3-{test_ts}",
            "title": "Old Backend Engineer",
            "company": "GitLab",
            "url": already_saved_url,
            "location": "Remote",
            "description": "Pre-existing job",
            "portal": "Greenhouse",
        },
    ]

    mock_emails = [
        # Email 1: Interview invitation
        {
            "id": "email-int-1",
            "sender": "talent@techcorp.io",
            "subject": "Invitation: Technical Interview for AI Role",
            "body": "Hi Ashutosh, we were impressed by your profile. Let's schedule a call on Calendly.",
            "recruiter_email": "talent@techcorp.io",
            "apply_urls": [],
            "is_interview": True,
            "date": "2026-10-04",
        },
        # Email 2: Standard newsletter / non-interview
        {
            "id": "email-news-2",
            "sender": "news@python.org",
            "subject": "Python Weekly Newsletter #600",
            "body": "Here are the top Python articles this week...",
            "recruiter_email": None,
            "apply_urls": [],
            "is_interview": False,
            "date": "2026-10-04",
        },
    ]

    def mock_analyze_match_side_effect(profile_path, job):
        if "Python AI" in job.get("title", ""):
            return {"match_score": 88, "matched_skills": ["Python", "AI Agent", "LLM"]}
        return {"match_score": 42, "matched_skills": []}

    with patch("antigravity_agent.ZeroLoginJobFetcher.get_all_jobs", return_value=mock_discovered_jobs) as mock_fetch, \
         patch("antigravity_agent.analyze_match", side_effect=mock_analyze_match_side_effect) as mock_match, \
         patch("antigravity_agent.ATSResumeGenerator.generate_tailored_resume") as mock_gen_resume, \
         patch("antigravity_agent.CoverLetterGenerator.generate") as mock_gen_cover, \
         patch("antigravity_agent.send_approval_request", return_value={"status": "sent"}) as mock_tg_approval, \
         patch("antigravity_agent.scan_job_emails", return_value=mock_emails) as mock_scan_emails, \
         patch("antigravity_agent.send_interview_alert", return_value={"status": "sent"}) as mock_tg_interview:

        stats = run_autonomous_cycle(
            keywords=["Python AI", "AI Agent", "LLM", "Automation"],
            min_match_score=65,
        )

        # 1. Verify Job Fetcher called with keywords
        mock_fetch.assert_called_once_with(keywords=["Python AI", "AI Agent", "LLM", "Automation"])

        # 2. Verify Stats
        assert stats["status"] == "success"
        assert stats["jobs_fetched"] == 3
        assert stats["jobs_evaluated"] == 2  # Already saved job was skipped
        assert stats["jobs_qualified"] == 1  # Only Job 1 scored >= 65
        assert stats["emails_scanned"] == 2
        assert stats["interviews_detected"] == 1

        # 3. Verify SQLite DB updates
        high_hash = generate_job_hash("Supabase", "Lead Python AI Engineer", qualified_url)
        db_job_high = get_job_by_hash(high_hash)
        assert db_job_high is not None
        assert db_job_high["match_score"] == 88
        assert "resume.txt" in db_job_high["tailored_resume_path"]
        assert "cover_letter.txt" in db_job_high["cover_letter_path"]

        low_hash = generate_job_hash("RoboCorp", "C++ Embedded Firmware Engineer", unqualified_url)
        db_job_low = get_job_by_hash(low_hash)
        assert db_job_low is not None
        assert db_job_low["match_score"] == 42
        assert db_job_low["tailored_resume_path"] is None

        # 4. Verify Asset Generation & File Paths
        assert mock_gen_resume.call_count == 1
        assert mock_gen_cover.call_count == 1

        resume_call_path = mock_gen_resume.call_args.kwargs["save_path"]
        cover_call_path = mock_gen_cover.call_args.kwargs["save_path"]
        assert f"tailored\\{high_hash}\\resume.txt" in resume_call_path or f"tailored/{high_hash}/resume.txt" in resume_call_path
        assert f"tailored\\{high_hash}\\cover_letter.txt" in cover_call_path or f"tailored/{high_hash}/cover_letter.txt" in cover_call_path

        # 5. Verify Telegram Approval Request
        mock_tg_approval.assert_called_once_with(
            job_hash=high_hash,
            title="Lead Python AI Engineer",
            company="Supabase",
            score=88,
            url=qualified_url,
        )

        # 6. Verify Telegram Interview Alert
        mock_tg_interview.assert_called_once_with(
            company="talent@techcorp.io",
            role="Invitation: Technical Interview for AI Role",
            snippet="Hi Ashutosh, we were impressed by your profile. Let's schedule a call on Calendly.",
        )

    print("[OK] Full autonomous cycle successfully verified with zero regressions.")


if __name__ == "__main__":
    test_google_antigravity_agent_initialization()
    test_scheduler_configuration()
    test_run_autonomous_cycle_end_to_end()
    print("\n All antigravity agent tests passed with exit code 0!")
