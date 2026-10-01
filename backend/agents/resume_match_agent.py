import json
from pathlib import Path

from services.job_matcher import JobMatcher


class ResumeMatchAgent:

    @staticmethod
    def match(jobs: list):

        profile_path = Path("data/profile.json")

        if not profile_path.exists():
            raise FileNotFoundError("Profile not found.")

        ranked_jobs = []

        for job in jobs:

            result = JobMatcher.match(
                str(profile_path),
                job.get("description", "")
            )

            ranked_jobs.append(
                {
                    **job,
                    **result
                }
            )

        ranked_jobs.sort(
            key=lambda x: x["match_score"],
            reverse=True
        )

        return ranked_jobs