"""
Integration test for Target Companies & India-Eligible Job Pipeline.
"""

from services.job_search import JobSearchService, is_eligible_for_india

def test_filtering_rules():
    print("--- 1. Testing India Eligibility Filter Rules ---")
    test_cases = [
        # (location, title, description, expected)
        ("Remote, Bangalore", "AI Engineer", "Build generative AI systems", True),
        ("India", "Software Engineer", "Remote work across India", True),
        ("Worldwide", "Backend Developer", "Open to all timezones", True),
        ("Global", "Prompt Engineer", "", True),
        ("APAC", "Solutions Architect", "", True),
        ("Anywhere", "Full Stack Engineer", "", True),
        ("Remote", "AI Automation Specialist", "", True),
        # Exclusions:
        ("Remote", "Federal Data Engineer", "Must be a US Citizen to apply", False),
        ("Remote", "Python Developer", "W2 Only position, no exceptions", False),
        ("Remote", "Frontend Dev", "Requires C2C contract with US entity", False),
        ("Remote", "Security Specialist", "Must reside in US or Canada", False),
        ("Remote - AMER", "Sales Engineer", "", False),
        ("Remote - DACH", "Payroll Manager", "", False),
        ("United States", "ML Engineer", "", False),
    ]

    for loc, title, desc, expected in test_cases:
        res = is_eligible_for_india(loc, title, desc)
        assert res == expected, f"Failed filter for ({loc}, {title}, {desc}): expected {expected}, got {res}"

    print("[OK] All 14 filtering test cases passed!")

def test_target_companies():
    print("\n--- 2. Testing Target Companies (Greenhouse & Ashby) ---")
    jobs = JobSearchService.fetch_all_target_companies(keyword="engineer")
    print(f"Discovered {len(jobs)} India-eligible engineering jobs across target companies.")
    assert len(jobs) > 0, "No target company jobs retrieved!"

    companies_found = set(j["company"] for j in jobs)
    print(f"Target companies represented: {companies_found}")
    for j in jobs[:3]:
        print(f"  [{j['portal']}] {j['company']} -> {j['title']} (Loc: {j['location']})")

def test_aggregators():
    print("\n--- 3. Testing Aggregators (Himalayas, WWR, Remotive, RemoteOK) ---")
    h_jobs = JobSearchService.fetch_himalayas(keyword="engineer")
    print(f"Himalayas (India) matches: {len(h_jobs)}")

    wwr_jobs = JobSearchService.fetch_wwr(keyword="engineer")
    print(f"WeWorkRemotely matches: {len(wwr_jobs)}")

    remotive_jobs = JobSearchService.fetch_remotive(keyword="python")
    print(f"Remotive matches: {len(remotive_jobs)}")

    remoteok_jobs = JobSearchService.fetch_remoteok(keyword="python")
    print(f"RemoteOK matches: {len(remoteok_jobs)}")

def test_unified_search():
    print("\n--- 4. Testing Unified Search Dispatcher ---")
    unified = JobSearchService.search(keyword="python", portal="All Sources (India Eligible)", max_total=10)
    print(f"Unified search retrieved {len(unified)} jobs:")
    for j in unified[:5]:
        print(f"  - [{j['portal']}] {j['company']} -- {j['title']} | Loc: {j['location']}")

    assert len(unified) > 0, "Unified search returned empty!"
    print("\n[SUCCESS] ALL PIPELINE TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_filtering_rules()
    test_target_companies()
    test_aggregators()
    test_unified_search()
