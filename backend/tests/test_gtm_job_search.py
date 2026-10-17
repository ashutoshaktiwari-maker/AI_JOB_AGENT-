"""
Unit & Integration Tests for GTM Engineering & Revenue Automation Job Search.

Verifies:
1. Strict code length constraint (< 200 lines).
2. Deduplicated Target Roles & Search Keywords.
3. Core Skills & Tooling Taxonomy for semantic matching & tailoring.
4. Public Ingestion Boards (Greenhouse, Ashby, Lever, Jobicy, Remotive).
5. Strict India-remote eligibility and exclusion filtering (including icims.com).
6. Standardized 7-key output schema.
7. ZeroLoginJobFetcher functionality.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.job_search import (
    BOARDS_CONFIG,
    CORE_SKILLS_TAXONOMY,
    FRICTION_ATS,
    LOCATION_ALLOW,
    SEARCH_KEYWORDS,
    TARGET_ROLES,
    JobSearchService,
    ZeroLoginJobFetcher,
    clean_html,
    is_eligible_for_india,
    normalize_job,
)


def test_code_under_200_lines():
    print("--- 1. Testing Code Line Count Constraint (< 200 lines) ---")
    file_path = backend_dir / "services" / "job_search.py"
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    line_count = len(lines)
    print(f"job_search.py total lines: {line_count}")
    assert line_count < 200, f"File exceeds 200 lines: {line_count} lines"
    print("[OK] Code line count is strictly under 200 lines.")


def test_gtm_roles_and_search_keywords():
    print("--- 2. Testing Target Roles & Search Keywords ---")
    expected_roles = [
        "GTM Engineer",
        "Revenue Operations Automation",
        "Marketing Automation Engineer",
        "Growth Engineer",
    ]
    assert TARGET_ROLES == expected_roles

    expected_keywords = [
        "GTM Engineer",
        "Revenue Operations",
        "Marketing Automation",
        "Growth Engineer",
        "RevOps Automation",
        "Inbound Automation",
    ]
    assert SEARCH_KEYWORDS == expected_keywords
    # Ensure no duplicates
    assert len(SEARCH_KEYWORDS) == len(set(SEARCH_KEYWORDS))
    print("[OK] Target Roles & deduplicated Search Keywords verified.")


def test_core_skills_taxonomy():
    print("--- 3. Testing Core Skills & Tooling Taxonomy ---")
    assert "Enrichment & Outbound Engines" in CORE_SKILLS_TAXONOMY
    assert "CRM & Marketing Automation" in CORE_SKILLS_TAXONOMY
    assert "Cold Outreach & Email Deliverability" in CORE_SKILLS_TAXONOMY
    assert "Workflow & Integration Automation" in CORE_SKILLS_TAXONOMY
    assert "Modern Stack" in CORE_SKILLS_TAXONOMY

    enrichment = CORE_SKILLS_TAXONOMY["Enrichment & Outbound Engines"]
    for tool in ["Clay", "Apollo.io", "ZoomInfo", "Clearbit"]:
        assert tool in enrichment

    crm = CORE_SKILLS_TAXONOMY["CRM & Marketing Automation"]
    for tool in ["HubSpot", "Salesforce", "Marketo", "Customer.io"]:
        assert tool in crm

    outreach = CORE_SKILLS_TAXONOMY["Cold Outreach & Email Deliverability"]
    for tool in ["Instantly.ai", "Smartlead", "Lemlist"]:
        assert tool in outreach

    workflow = CORE_SKILLS_TAXONOMY["Workflow & Integration Automation"]
    for tool in ["Zapier", "Make", "n8n", "Webhooks", "REST APIs"]:
        assert tool in workflow

    print("[OK] Core Skills & Tooling Taxonomy verified.")


def test_public_ingestion_endpoints_config():
    print("--- 4. Testing Public Boards Configuration ---")
    assert BOARDS_CONFIG["greenhouse"] == ["hubspot", "segment", "zapier", "postman", "gitlab", "automattic"]
    assert BOARDS_CONFIG["ashby"] == ["clay", "apollo", "customerio", "replit", "linear", "deel"]
    assert BOARDS_CONFIG["lever"] == ["lemlist", "buffer", "kinsta"]
    print("[OK] Public ingestion boards configured properly.")


def test_india_remote_and_friction_ats_filters():
    print("--- 5. Testing Filtering Rules ---")
    # 1. Friction ATS Rejection
    assert not is_eligible_for_india(location="Remote", url="https://acme.myworkdayjobs.com/job/1")
    assert not is_eligible_for_india(location="Remote", url="https://acme.taleo.net/job/2")
    assert not is_eligible_for_india(location="Remote", url="https://acme.icims.com/job/3")

    # 2. Exclusions
    exclusions = [
        ("Remote", "Position for US Citizen only"),
        ("Remote", "W2 only engagement"),
        ("Remote", "US/EU only candidates"),
        ("Remote", "Only open to C2C"),
        ("Remote", "Must reside in US"),
        ("Remote", "Position is US only"),
        ("Remote", "UK only applicants"),
        ("Remote", "Canada only applicants"),
    ]
    for loc, desc in exclusions:
        assert not is_eligible_for_india(location=loc, description=desc), f"Should reject: {desc}"

    # 3. Allow Valid Remote & India positions
    valid_cases = [
        ("India", "GTM Engineer"),
        ("Bengaluru, India", "Revenue Operations"),
        ("Worldwide", "Marketing Automation"),
        ("Anywhere", "Growth Engineer"),
        ("Global", "RevOps Automation"),
        ("APAC", "Inbound Automation"),
        ("Remote", "Lead GTM Automation Engineer"),
    ]
    for loc, desc in valid_cases:
        assert is_eligible_for_india(location=loc, description=desc), f"Should allow: {loc} / {desc}"

    # 4. Reject Non-remote Non-India
    assert not is_eligible_for_india(location="Berlin, Germany", description="Onsite coordinator")
    assert not is_eligible_for_india(location="Dallas, TX", description="In-office accountant")
    print("[OK] Eligibility and friction ATS filters verified.")


def test_normalization_schema():
    print("--- 6. Testing Unified Output Schema ---")
    job = normalize_job(
        id_=9901,
        title="  GTM Systems Engineer ",
        company=" Clay ",
        url=" https://clay.com/jobs/9901 ",
        location=" Remote, Worldwide ",
        description="<p>Automate outbound engines with <b>Clay</b> and <b>Apollo</b>.</p>",
        portal=" Ashby (Clay) ",
    )
    expected_keys = {"id", "title", "company", "url", "location", "description", "portal"}
    assert set(job.keys()) == expected_keys
    for k, v in job.items():
        assert isinstance(v, str)
    assert job["id"] == "9901"
    assert job["title"] == "GTM Systems Engineer"
    assert job["company"] == "Clay"
    assert job["url"] == "https://clay.com/jobs/9901"
    assert job["location"] == "Remote, Worldwide"
    assert job["description"] == "Automate outbound engines with Clay and Apollo."
    assert job["portal"] == "Ashby (Clay)"
    print("[OK] Unified output schema verified.")


def test_zero_login_job_fetcher():
    print("--- 7. Testing ZeroLoginJobFetcher ---")
    mock_jobs = [
        {
            "id": "1",
            "title": "Senior GTM Engineer",
            "company": "HubSpot",
            "url": "https://hubspot.com/job/1",
            "location": "Remote",
            "description": "Managing HubSpot, Salesforce, and n8n pipelines.",
            "portal": "Greenhouse (Hubspot)",
        },
        {
            "id": "2",
            "title": "Revenue Operations Automation Lead",
            "company": "Apollo",
            "url": "https://apollo.io/job/2",
            "location": "Worldwide",
            "description": "Apollo and Clay outbound automation.",
            "portal": "Ashby (Apollo)",
        },
    ]

    with patch.object(JobSearchService, "fetch_all_sources", return_value=mock_jobs):
        jobs = ZeroLoginJobFetcher.get_all_jobs(keywords=["GTM Engineer", "Revenue Operations"])
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Senior GTM Engineer"
        assert jobs[1]["title"] == "Revenue Operations Automation Lead"
    print("[OK] ZeroLoginJobFetcher successfully tested with mock data.")


if __name__ == "__main__":
    test_code_under_200_lines()
    test_gtm_roles_and_search_keywords()
    test_core_skills_taxonomy()
    test_public_ingestion_endpoints_config()
    test_india_remote_and_friction_ats_filters()
    test_normalization_schema()
    test_zero_login_job_fetcher()
    print("\nALL GTM JOB SEARCH TESTS PASSED SUCCESSFULLY! [SUCCESS]")
