import json
import os
from typing import Any, Dict, Union

from match_agent import analyze_match


class JobMatcher:

    @staticmethod
    def match(profile_or_path: Union[str, Dict[str, Any]], job_description: str) -> dict:
        """
        Match profile against job description using AI Match Engine.

        Args:
            profile_or_path: File path to profile.json or a profile dictionary.
            job_description: Target job description text.

        Returns:
            dict containing match_score, matched_skills, missing_skills, short_summary, recommendation.
        """
        if isinstance(profile_or_path, str) and os.path.exists(profile_or_path):
            with open(profile_or_path, "r", encoding="utf-8") as f:
                profile_data = json.load(f)
        else:
            profile_data = profile_or_path

        return analyze_match(profile_data, job_description)