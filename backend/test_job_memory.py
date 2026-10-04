"""
Unit tests for JobMemory persistent storage layer.
"""

from database.job_memory import (
    generate_job_hash,
    is_job_saved,
    save_discovered_job,
    update_job_assets,
    mark_job_status,
    get_pending_jobs,
)

def test_job_memory():
    print("--- 1. Testing Hash Generation ---")
    h1 = generate_job_hash("GitLab", "Senior Backend Engineer", "https://job-boards.greenhouse.io/gitlab/jobs/123")
    h2 = generate_job_hash("gitlab ", " Senior Backend Engineer ", "https://job-boards.greenhouse.io/gitlab/jobs/123")
    assert h1 == h2, "Hashes should be identical after normalization"
    assert len(h1) == 64, "SHA256 hex digest should be 64 characters"
    print("[OK] Hash generation passed:", h1[:16] + "...")

    import time
    test_url = f"https://job-boards.greenhouse.io/test/jobs/{int(time.time()*1000)}"
    assert not is_job_saved(test_url), "Job should not be saved yet"

    job_data = {
        "company": "Supabase",
        "title": "AI Platform Engineer",
        "location": "Remote, Global",
        "portal": "Ashby (Supabase)",
        "url": test_url,
        "description": "Building scalable database systems with vector indexing and AI.",
    }
    j_hash = save_discovered_job(job_data, match_score=92)
    assert j_hash == generate_job_hash(job_data["company"], job_data["title"], test_url)
    assert is_job_saved(test_url), "Job should now be marked as saved"
    print("[OK] Job saved and deduplication check passed")

    print("\n--- 3. Testing Asset Updates ---")
    r_path = "backend/data/tailored/supabase_resume.txt"
    cl_path = "backend/data/tailored/supabase_cover_letter.txt"
    updated = update_job_assets(j_hash, r_path, cl_path)
    assert updated, "Asset update should return True"
    print("[OK] Asset paths updated successfully")

    print("\n--- 4. Testing Pending Jobs Retrieval ---")
    pending = get_pending_jobs(limit=10)
    assert len(pending) > 0, "Should have at least 1 pending job"
    found_job = next((j for j in pending if j["job_hash"] == j_hash), None)
    assert found_job is not None, "Saved job should be present in pending jobs"
    assert found_job["match_score"] == 92
    assert found_job["tailored_resume_path"] == r_path
    assert found_job["cover_letter_path"] == cl_path
    assert found_job["status"] == "pending_review"
    print("[OK] Pending jobs retrieval verified")

    print("\n--- 5. Testing Status Updates ---")
    mark_job_status(j_hash, "applied")
    pending_after = get_pending_jobs(limit=10)
    assert not any(j["job_hash"] == j_hash for j in pending_after), "Job should no longer be pending after applying"

    # Verify invalid status rejection
    try:
        mark_job_status(j_hash, "invalid_status_xyz")
        assert False, "Should raise ValueError on invalid status"
    except ValueError:
        print("[OK] Invalid status properly rejected")

    print("\n[SUCCESS] ALL JOB MEMORY TESTS PASSED!")

if __name__ == "__main__":
    test_job_memory()
