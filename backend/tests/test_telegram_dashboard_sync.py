"""
Unit & Integration Test for Telegram-to-Dashboard Application Sync.
Verifies:
1. Real-time and periodic synchronization from jobs_memory.db into applications.db.
2. Applications submitted via Telegram appear immediately in get_all_applications().
3. Dashboard metric counters reflect Telegram-applied positions.
4. Idempotency (prevent duplicate insertions of the same applied job).
"""

import sys
import time
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from database.job_memory import (
    save_discovered_job,
    update_job_assets,
    mark_job_status,
    init_db as init_job_memory,
)
from database.db import db


def test_telegram_to_dashboard_sync():
    print("--- 1. Testing Telegram-to-Dashboard Synchronization ---")
    init_job_memory()

    # Generate a unique test job
    unique_ts = int(time.time() * 1000)
    job_url = f"https://jobs.ashbyhq.com/sync-test-co/eng/{unique_ts}"
    job_dict = {
        "company": f"SyncTestCo_{unique_ts}",
        "title": "Lead Automation Architect",
        "url": job_url,
        "location": "Remote, Global",
        "portal": "Ashby",
        "description": "Building mission-critical workflow systems.",
    }

    # Simulate job discovery & match score
    job_hash = save_discovered_job(job_dict, match_score=96)
    update_job_assets(
        job_hash,
        resume_path="backend/data/tailored/test_resume.txt",
        cover_letter_path="backend/data/tailored/test_cover.txt",
    )

    # Simulate user approving and applying via Telegram
    mark_job_status(job_hash, "applied")

    # Sync to dashboard database
    new_synced = db.sync_from_agent_memory()
    assert new_synced >= 1, "Expected at least 1 new application to be synced."

    # Verify presence in get_all_applications
    all_apps = db.get_all_applications()
    matching = [a for a in all_apps if a.get("apply_url") == job_url]
    assert len(matching) == 1, f"Expected exactly 1 record for URL {job_url}, found {len(matching)}"

    synced_app = matching[0]
    assert synced_app["company"] == f"SyncTestCo_{unique_ts}"
    assert synced_app["role"] == "Lead Automation Architect"
    assert synced_app["status"] == "Applied"
    assert "Telegram Agent" in (synced_app["notes"] or "")
    assert "96%" in (synced_app["notes"] or "")
    print("[OK] Job applied via Telegram successfully synced to applications tracker.")

    # Test idempotency (calling sync again should not duplicate)
    second_sync = db.sync_from_agent_memory()
    assert second_sync == 0, f"Expected 0 duplicate syncs, got {second_sync}"
    all_apps_after = db.get_all_applications()
    matching_after = [a for a in all_apps_after if a.get("apply_url") == job_url]
    assert len(matching_after) == 1, "Duplicate record detected after second sync."
    print("[OK] Sync idempotency verified (zero duplicate records).")

    # Test dashboard stats
    stats = db.get_stats()
    assert stats["total"] >= 1
    assert stats["applied"] >= 1
    print(f"[OK] Dashboard stats updated: {stats}")


if __name__ == "__main__":
    test_telegram_to_dashboard_sync()
    print("\nALL TELEGRAM-TO-DASHBOARD SYNC TESTS PASSED! [SUCCESS]")
