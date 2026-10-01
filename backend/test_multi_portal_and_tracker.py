"""
Test script for Multi-Portal Job Search and Daily Job & Keyword Tracker.
"""

from services.job_search import JobSearchService
from services.daily_job_tracker import DailyJobTracker

def test_daily_tracker_and_portals():
    print("--- 1. Testing Daily Job Tracker ---")
    email = DailyJobTracker.get_tracked_email()
    print(f"Tracked Email: {email}")
    assert email == "ashutosh.aktiwari@gmail.com", f"Unexpected email: {email}"

    keywords = DailyJobTracker.get_tracked_keywords()
    print(f"Tracked Keywords ({len(keywords)}): {keywords}")
    assert len(keywords) >= 5, "Expected at least 5 default keywords"

    # Test adding and removing keyword
    test_kw = "TestKeywordAutomation"
    DailyJobTracker.add_tracked_keyword(test_kw)
    assert test_kw in DailyJobTracker.get_tracked_keywords()
    DailyJobTracker.remove_tracked_keyword(test_kw)
    assert test_kw not in DailyJobTracker.get_tracked_keywords()
    print("Keyword management test: PASS")

    # Test logging
    DailyJobTracker.log_search(
        keyword="AI Automation",
        portal="All Portals",
        jobs_count=15,
        email=email
    )
    history = DailyJobTracker.get_history(limit=5)
    print(f"Latest search log: {history[0]}")
    assert history[0]["keyword"] == "AI Automation"
    assert history[0]["email"] == email
    print("Search log test: PASS")

    print("\n--- 2. Testing Multi-Portal Search ---")
    jobs = JobSearchService.search(keyword="Python", portal="All Portals", max_total=6)
    print(f"Fetched {len(jobs)} jobs across portals")
    assert len(jobs) > 0, "No jobs returned!"

    portals_found = set(j["portal"] for j in jobs)
    print(f"Portals represented in sample: {portals_found}")
    for j in jobs[:3]:
        print(f"  [{j['portal']}] {j['company']} -> {j['title']} (URL: {bool(j.get('url'))})")

    print("\nALL MULTI-PORTAL & TRACKER TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_daily_tracker_and_portals()
