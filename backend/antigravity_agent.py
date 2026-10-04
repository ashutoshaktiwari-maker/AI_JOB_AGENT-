"""
Autonomous 24/7 AI Job Agent Loop.

Powered by Google Antigravity SDK and APScheduler.

Workflow:
1. Fetch remote job postings across zero-login boards using ZeroLoginJobFetcher.
2. Deduplicate against SQLite database (saved_jobs).
3. Evaluate candidate-job fit using match_agent against candidate profile.
4. If match_score >= 65:
   - Generate tailored ATS resume to backend/data/tailored/{job_hash}/resume.txt
   - Generate persuasive cover letter to backend/data/tailored/{job_hash}/cover_letter.txt
   - Record asset paths in SQLite
   - Dispatch interactive Telegram approval request with [Apply Yes] / [Skip No] buttons.
5. Ingest unread job-related emails from Gmail and send immediate interview alerts.
6. Run autonomously every 2 hours via APScheduler.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure backend and repository root are on sys.path
backend_dir = Path(__file__).resolve().parent
root_dir = backend_dir.parent
for p in [backend_dir, root_dir]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv

# Load environment variables
def _load_env() -> None:
    backend_env = backend_dir / ".env"
    root_env = root_dir / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
    elif root_env.exists():
        load_dotenv(root_env)
    else:
        load_dotenv()

_load_env()

# Import Google Antigravity SDK
from google.antigravity import Agent, LocalAgentConfig

# Import APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

# Import Database & Job Memory
try:
    from database.job_memory import (
        init_db,
        is_job_saved,
        save_discovered_job,
        update_job_assets,
    )
except ImportError:
    from backend.database.job_memory import (
        init_db,
        is_job_saved,
        save_discovered_job,
        update_job_assets,
    )

# Import Matching Agent
try:
    from match_agent import analyze_match
except ImportError:
    from backend.match_agent import analyze_match

# Import Services
try:
    from services.job_search import ZeroLoginJobFetcher
    from services.resume_generator import ATSResumeGenerator
    from services.cover_letter_generator import CoverLetterGenerator
    from services.telegram_notifier import (
        send_approval_request,
        send_interview_alert,
    )
    from services.gmail_job_reader import scan_job_emails
except ImportError:
    from backend.services.job_search import ZeroLoginJobFetcher
    from backend.services.resume_generator import ATSResumeGenerator
    from backend.services.cover_letter_generator import CoverLetterGenerator
    from backend.services.telegram_notifier import (
        send_approval_request,
        send_interview_alert,
    )
    from backend.services.gmail_job_reader import scan_job_emails

logger = logging.getLogger("antigravity_agent")

DEFAULT_KEYWORDS: List[str] = ["Python AI", "AI Agent", "LLM", "Automation"]
MIN_MATCH_THRESHOLD: int = 65


def resolve_profile_path() -> Path:
    """Resolves absolute path to backend/data/profile.json."""
    candidates = [
        backend_dir / "data" / "profile.json",
        root_dir / "backend" / "data" / "profile.json",
        Path("backend/data/profile.json"),
        Path("data/profile.json"),
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    # Default fallback
    target = backend_dir / "data" / "profile.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def resolve_tailored_dir(job_hash: str) -> Path:
    """Resolves and creates directory for tailored assets: backend/data/tailored/{job_hash}."""
    tailored_dir = backend_dir / "data" / "tailored" / job_hash
    tailored_dir.mkdir(parents=True, exist_ok=True)
    return tailored_dir


def run_autonomous_cycle(
    keywords: Optional[List[str]] = None,
    min_match_score: int = MIN_MATCH_THRESHOLD,
) -> Dict[str, Any]:
    """
    Executes a single autonomous cycle:
    a. Ingest jobs via ZeroLoginJobFetcher across target keywords.
    b. Deduplicate and score each new job against candidate profile.
       If score >= min_match_score (65):
         - Generate tailored ATS resume
         - Generate tailored cover letter
         - Store assets and update SQLite
         - Dispatch Telegram approval request with inline buttons
    c. Scan Gmail for keyword notifications and interview invitations.
    """
    target_keywords = keywords or DEFAULT_KEYWORDS
    logger.info("==================================================")
    logger.info("Starting Autonomous Job Cycle with keywords: %s", target_keywords)
    logger.info("==================================================")

    init_db()
    profile_path = resolve_profile_path()

    stats: Dict[str, Any] = {
        "status": "success",
        "keywords": target_keywords,
        "jobs_fetched": 0,
        "jobs_evaluated": 0,
        "jobs_qualified": 0,
        "emails_scanned": 0,
        "interviews_detected": 0,
        "processed_jobs": [],
    }

    # Step a: Zero-Login Job Discovery
    logger.info("[Step A] Fetching jobs from zero-login endpoints...")
    try:
        discovered_jobs = ZeroLoginJobFetcher.get_all_jobs(keywords=target_keywords)
        stats["jobs_fetched"] = len(discovered_jobs)
        logger.info("Discovered %d remote opportunities.", len(discovered_jobs))
    except Exception as exc:
        logger.error("ZeroLoginJobFetcher failed: %s", exc)
        discovered_jobs = []

    # Step b: Evaluate new jobs, generate tailored assets, notify Telegram
    logger.info("[Step B] Evaluating and filtering opportunities...")
    for job in discovered_jobs:
        url = (job.get("url") or "").strip()
        if not url:
            continue

        # Check SQLite deduplication
        if is_job_saved(url):
            logger.debug("Skipping already saved job: %s", url)
            continue

        stats["jobs_evaluated"] += 1
        company = job.get("company", "Unknown Company")
        title = job.get("title", "Unknown Role")
        logger.info("Evaluating: '%s' at '%s'", title, company)

        # Match evaluation against candidate profile
        try:
            match_res = analyze_match(str(profile_path), job)
            score = int(match_res.get("match_score", 0))
        except Exception as match_err:
            logger.warning("Match analysis error for %s (%s): %s", title, company, match_err)
            score = 0

        # Save discovered job in SQLite
        job_hash = save_discovered_job(job, match_score=score)
        job_record = {
            "job_hash": job_hash,
            "title": title,
            "company": company,
            "score": score,
            "url": url,
            "qualified": score >= min_match_score,
        }

        # If score meets qualification threshold (>= 65), generate assets and alert
        if score >= min_match_score:
            stats["jobs_qualified"] += 1
            logger.info("🎯 High match (%d%% >= %d%%)! Generating tailored assets for %s...", score, min_match_score, job_hash)

            tailored_dir = resolve_tailored_dir(job_hash)
            resume_path = tailored_dir / "resume.txt"
            cover_letter_path = tailored_dir / "cover_letter.txt"

            jd_text = job.get("description", "") or f"Role: {title}\nCompany: {company}\nDetails: {url}"

            # 1. Generate tailored ATS Resume
            try:
                ATSResumeGenerator.generate_tailored_resume(
                    resume=str(profile_path),
                    job_description=jd_text,
                    save_path=str(resume_path),
                )
            except Exception as res_err:
                logger.error("Failed to generate tailored resume for %s: %s", job_hash, res_err)

            # 2. Generate Cover Letter
            try:
                CoverLetterGenerator.generate(
                    resume=str(profile_path),
                    job_description=jd_text,
                    company_name=company,
                    role_title=title,
                    save_path=str(cover_letter_path),
                )
            except Exception as cl_err:
                logger.error("Failed to generate cover letter for %s: %s", job_hash, cl_err)

            # 3. Update SQLite with asset paths
            update_job_assets(
                job_hash=job_hash,
                resume_path=str(resume_path),
                cover_letter_path=str(cover_letter_path),
            )
            job_record["resume_path"] = str(resume_path)
            job_record["cover_letter_path"] = str(cover_letter_path)

            # 4. Dispatch Telegram interactive approval request
            try:
                telegram_resp = send_approval_request(
                    job_hash=job_hash,
                    title=title,
                    company=company,
                    score=score,
                    url=url,
                )
                job_record["telegram_status"] = telegram_resp.get("status")
                logger.info("Telegram approval prompt dispatched for %s (%s).", job_hash, telegram_resp.get("status"))
            except Exception as tg_err:
                logger.error("Telegram approval prompt failed for %s: %s", job_hash, tg_err)
                job_record["telegram_status"] = "error"

        stats["processed_jobs"].append(job_record)

    # Step c: Email Ingestion & Interview Discovery
    logger.info("[Step C] Scanning Gmail for job notifications and interview invites...")
    try:
        scanned_emails = scan_job_emails(keywords=target_keywords)
        stats["emails_scanned"] = len(scanned_emails)

        for email_item in scanned_emails:
            if email_item.get("is_interview"):
                stats["interviews_detected"] += 1
                company_name = email_item.get("sender", "Recruiter / Hiring Team")
                role_name = email_item.get("subject", "Interview Invitation")
                snippet = email_item.get("body", "")[:350]

                logger.info("🚨 Interview alert detected from '%s': '%s'", company_name, role_name)
                try:
                    send_interview_alert(
                        company=company_name,
                        role=role_name,
                        snippet=snippet,
                    )
                except Exception as alert_err:
                    logger.error("Failed to send interview alert: %s", alert_err)
    except Exception as email_err:
        logger.warning("Gmail scan encountered an issue or OAuth credentials not ready: %s", email_err)

    logger.info(
        "Autonomous cycle completed: %d evaluated, %d qualified, %d emails scanned, %d interviews.",
        stats["jobs_evaluated"],
        stats["jobs_qualified"],
        stats["emails_scanned"],
        stats["interviews_detected"],
    )
    return stats


def create_antigravity_agent() -> Agent:
    """
    Initializes a Google Antigravity Agent configured with autonomous job cycle tools.
    """
    config = LocalAgentConfig(
        system_instructions=(
            "You are the Autonomous AI Job Application Agent operating 24/7. "
            "Your duties are:\n"
            "1. Continuously discover zero-login remote job listings.\n"
            "2. Evaluate candidate profile alignment using strict technical matching.\n"
            "3. Generate ATS-optimized resumes and targeted cover letters without fabrication.\n"
            "4. Send instant interactive Telegram prompts for candidate sign-off.\n"
            "5. Monitor email communications for interview and screening invitations."
        ),
        tools=[run_autonomous_cycle],
    )
    return Agent(config=config)


# Module-level agent instance
autonomous_agent = create_antigravity_agent()


def build_scheduler(
    hours: int = 2,
    blocking: bool = True,
) -> BlockingScheduler | BackgroundScheduler:
    """
    Builds and configures an APScheduler instance to run run_autonomous_cycle every `hours` hours.
    """
    scheduler = BlockingScheduler() if blocking else BackgroundScheduler()
    scheduler.add_job(
        run_autonomous_cycle,
        trigger="interval",
        hours=hours,
        id="autonomous_job_agent_cycle",
        replace_existing=True,
    )
    return scheduler


def start_scheduler(
    hours: int = 2,
    blocking: bool = True,
    run_immediately: bool = True,
) -> BlockingScheduler | BackgroundScheduler:
    """
    Starts the APScheduler loop. Runs an initial cycle immediately if requested.
    """
    if run_immediately:
        logger.info("Executing initial autonomous cycle on startup...")
        try:
            run_autonomous_cycle()
        except Exception as exc:
            logger.error("Initial autonomous cycle error: %s", exc)

    scheduler = build_scheduler(hours=hours, blocking=blocking)
    logger.info("APScheduler initialized: running every %d hours (blocking=%s).", hours, blocking)
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print("=" * 60)
    print("🤖 Starting 24/7 Autonomous AI Job Agent (Google Antigravity)")
    print("   Schedule: Every 2 hours")
    print("=" * 60)
    start_scheduler(hours=2, blocking=True, run_immediately=True)
