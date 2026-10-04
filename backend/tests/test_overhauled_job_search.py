"""
Integration & Unit Tests for Overhauled job_search.py
Verifies:
1. Strict India Remote Eligibility Filtering:
   - ALLOW: 'india', 'worldwide', 'anywhere', 'global', 'apac', 'remote'
   - REJECT: 'us citizen', 'w2 only', 'us/eu only', 'c2c', 'must reside in us', 'us only', 'uk only', 'canada only'
   - REJECT legacy friction ATS URLs: 'myworkdayjobs.com', 'taleo.net'
2. Schema Normalization:
   - Exactly {"id": str, "title": str, "company": str, "url": str, "location": str, "description": str, "portal": str}
3. Public zero-login multi-source scrapers:
   - Greenhouse, Ashby, Lever, Jobicy, Remotive, RemoteOK, Himalayas, Arbeitnow, WeWorkRemotely, Dev.to
4. Compatibility with backend.database.job_memory
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.job_search import (
    JobSearchService,
    is_eligible_for_india,
    normalize_job,
    clean_html,
)
from database.job_memory import save_discovered_job, is_job_saved, get_pending_jobs


def test_clean_html():
    raw = "<p>Join <strong>our</strong> team &amp; build AI! <br/>Details...</p>"
    cleaned = clean_html(raw)
    assert cleaned == "Join our team & build AI! Details..."
    assert clean_html("") == ""
    assert clean_html(None) == ""
    print("test_clean_html passed.")


def test_filtering_eligibility():
    # 1. Reject Legacy URLs
    assert not is_eligible_for_india(location="Remote", url="https://acme.myworkdayjobs.com/job/123")
    assert not is_eligible_for_india(location="Remote", url="https://corp.taleo.net/career/apply")

    # 2. Reject Disallowed phrases in description or location
    reject_cases = [
        ("Remote", "We require US Citizen for clearance"),
        ("Remote", "This position is W2 only"),
        ("Remote", "Hiring is US/EU only"),
        ("Remote", "C2C candidates welcome"),
        ("Remote", "Applicant must reside in US"),
        ("Remote", "Must reside in the US"),
        ("Remote", "Position is US only"),
        ("Remote", "UK only applicants"),
        ("Remote", "Canada only applicants"),
        ("Remote - US Only", "Great remote software job"),
    ]
    for loc, desc in reject_cases:
        assert not is_eligible_for_india(location=loc, description=desc), f"Failed to reject: {loc} / {desc}"

    # 3. Allow valid India/Global/APAC/Worldwide/Remote cases
    allow_cases = [
        ("India", "Software Engineer"),
        ("Bengaluru, India", "Backend Engineer"),
        ("Worldwide", "Frontend Developer"),
        ("Anywhere", "DevOps Engineer"),
        ("Global", "AI Research Engineer"),
        ("APAC", "Data Scientist"),
        ("Remote", "Full Stack Developer"),
        ("Worldwide (Remote)", "Staff Engineer"),
    ]
    for loc, desc in allow_cases:
        assert is_eligible_for_india(location=loc, description=desc), f"Failed to allow: {loc} / {desc}"

    # 4. Reject local non-remote non-India jobs
    assert not is_eligible_for_india(location="Berlin, Germany", description="Onsite warehouse manager")
    assert not is_eligible_for_india(location="Austin, Texas", description="Onsite lab technician")

    print("test_filtering_eligibility passed.")


def test_normalization_schema():
    job = normalize_job(
        id_=12345,
        title="  Staff AI Engineer  ",
        company=" Acme Corp ",
        url=" https://acme.com/jobs/123 ",
        location=" Remote, Worldwide ",
        description="<p>Build <b>GenAI</b> systems!</p>",
        portal=" Greenhouse (Acme) ",
    )

    required_keys = {"id", "title", "company", "url", "location", "description", "portal"}
    assert set(job.keys()) == required_keys, f"Keys mismatch: {set(job.keys())}"

    for k, v in job.items():
        assert isinstance(v, str), f"Key {k} is not str: {type(v)}"

    assert job["id"] == "12345"
    assert job["title"] == "Staff AI Engineer"
    assert job["company"] == "Acme Corp"
    assert job["url"] == "https://acme.com/jobs/123"
    assert job["location"] == "Remote, Worldwide"
    assert job["description"] == "Build GenAI systems!"
    assert job["portal"] == "Greenhouse (Acme)"

    print("test_normalization_schema passed.")


def test_public_endpoints_and_search():
    # 1. Test Ashby boards (e.g. Supabase, Linear)
    ashby_jobs = JobSearchService._fetch_ashby_board("Supabase", "supabase")
    print(f"Fetched {len(ashby_jobs)} eligible jobs from Ashby (Supabase)")
    assert isinstance(ashby_jobs, list)
    if ashby_jobs:
        assert set(ashby_jobs[0].keys()) == {"id", "title", "company", "url", "location", "description", "portal"}

    # 2. Test Greenhouse boards (e.g. Canonical, GitLab)
    gh_jobs = JobSearchService._fetch_greenhouse_board("Canonical", "canonical")
    print(f"Fetched {len(gh_jobs)} eligible jobs from Greenhouse (Canonical)")
    assert isinstance(gh_jobs, list)
    if gh_jobs:
        assert set(gh_jobs[0].keys()) == {"id", "title", "company", "url", "location", "description", "portal"}

    # 3. Test Lever boards (e.g. Palantir)
    lever_jobs = JobSearchService._fetch_lever_board("Palantir", "palantir")
    print(f"Fetched {len(lever_jobs)} eligible jobs from Lever (Palantir)")
    assert isinstance(lever_jobs, list)
    if lever_jobs:
        assert set(lever_jobs[0].keys()) == {"id", "title", "company", "url", "location", "description", "portal"}

    # 4. Test Aggregators
    jobicy_jobs = JobSearchService.fetch_jobicy()
    print(f"Fetched {len(jobicy_jobs)} eligible jobs from Jobicy")
    assert isinstance(jobicy_jobs, list)

    himalayas_jobs = JobSearchService.fetch_himalayas()
    print(f"Fetched {len(himalayas_jobs)} eligible jobs from Himalayas")
    assert isinstance(himalayas_jobs, list)

    wwr_jobs = JobSearchService.fetch_weworkremotely()
    print(f"Fetched {len(wwr_jobs)} eligible jobs from WeWorkRemotely RSS")
    assert isinstance(wwr_jobs, list)

    # 5. Test Unified Search Dispatcher
    unified = JobSearchService.search(keyword="Python", max_total=10)
    print(f"Fetched {len(unified)} jobs from unified search for 'Python'")
    assert len(unified) > 0
    assert len(unified) <= 10

    for j in unified:
        assert set(j.keys()) == {"id", "title", "company", "url", "location", "description", "portal"}
        for k, v in j.items():
            assert isinstance(v, str)
        # Verify no forbidden ATS links
        assert "myworkdayjobs.com" not in j["url"].lower()
        assert "taleo.net" not in j["url"].lower()

    # 6. Test DB saving compatibility
    sample = unified[0]
    job_hash = save_discovered_job(sample, match_score=88)
    assert isinstance(job_hash, str) and len(job_hash) == 64
    assert is_job_saved(sample["url"])

    print("test_public_endpoints_and_search passed successfully!")


if __name__ == "__main__":
    test_clean_html()
    test_filtering_eligibility()
    test_normalization_schema()
    test_public_endpoints_and_search()
    print("\nALL JOB SEARCH OVERHAUL TESTS PASSED SUCCESSFULLY! [SUCCESS]")
