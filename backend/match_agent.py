import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Union

from tools.llm import LLM

logger = logging.getLogger(__name__)


def _extract_skills_from_text(text: str) -> List[str]:
    """Helper to extract skills from raw resume or job text if not provided as a list."""
    if not text:
        return []
    # Check for "Core Skills" or "Skills" section
    skills_match = re.search(r"(?:Core\s+)?Skills[:\n\r]+(.*?)(?:\n\s*\n|[A-Z][a-zA-Z\s]{2,}:|$)", text, re.IGNORECASE | re.DOTALL)
    if skills_match:
        section = skills_match.group(1).strip()
        # Split by bullet, pipe, comma, or newline
        items = re.split(r"[\u2022\u2023\u25e6\u2043\u2219,\|\n]+", section)
        skills = [s.strip() for s in items if s.strip() and len(s.strip()) < 40]
        if skills:
            return skills

    # Fallback to common tech keywords search
    common_keywords = [
        "Python", "FastAPI", "Django", "Flask", "JavaScript", "TypeScript", "React",
        "Node.js", "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Docker",
        "Kubernetes", "AWS", "GCP", "Azure", "CI/CD", "Git", "REST APIs", "GraphQL",
        "LLM", "RAG", "Machine Learning", "AI Agents", "Prompt Engineering", "Streamlit",
        "Pandas", "NumPy", "PyTorch", "TensorFlow", "n8n", "Make.com"
    ]
    found = [kw for kw in common_keywords if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE)]
    return found


def _fallback_match(candidate_skills: List[str], candidate_text: str, jd_text: str) -> Dict[str, Any]:
    """Deterministic fallback matching algorithm when LLM is unavailable."""
    jd_lower = jd_text.lower()

    # Identify candidate skills found in job description
    matched = []
    missing_candidate_skills = []
    for skill in candidate_skills:
        if re.search(rf"\b{re.escape(skill.lower())}\b", jd_lower):
            matched.append(skill)
        else:
            missing_candidate_skills.append(skill)

    # Extract required skills from JD that candidate does not possess
    jd_skills = _extract_skills_from_text(jd_text)
    candidate_skills_lower = {s.lower() for s in candidate_skills}
    missing_from_jd = [
        s for s in jd_skills
        if s.lower() not in candidate_skills_lower and s.lower() not in candidate_text.lower()
    ]

    missing = list(dict.fromkeys(missing_from_jd))
    if not missing and jd_skills:
        missing = [s for s in jd_skills if s not in matched]

    total_reqs = len(matched) + len(missing)
    if total_reqs > 0:
        raw_score = (len(matched) / total_reqs) * 100
    elif candidate_skills:
        raw_score = (len(matched) / len(candidate_skills)) * 100
    else:
        raw_score = 50

    match_score = max(0, min(100, round(raw_score)))

    if match_score >= 75:
        recommendation = "Apply"
        summary = f"Strong match ({match_score}%). Matches key requirements including {', '.join(matched[:3])}."
    elif match_score >= 50:
        recommendation = "Tailor Resume"
        summary = f"Moderate match ({match_score}%). Possesses {', '.join(matched[:3]) if matched else 'relevant foundation'}, but lacks {', '.join(missing[:3]) if missing else 'certain required stack skills'}."
    else:
        recommendation = "Skip"
        summary = f"Low match ({match_score}%). Significant skill gaps identified in {', '.join(missing[:3]) if missing else 'core prerequisites'}."

    return {
        "match_score": match_score,
        "matched_skills": matched,
        "missing_skills": missing,
        "short_summary": summary,
        "summary": summary,
        "recommendation": recommendation,
    }


def analyze_match(resume: Union[Dict[str, Any], str], job: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """
    Compare parsed resume with Job Description.

    Returns:
      - match_score (int 0-100)
      - matched_skills (list of str)
      - missing_skills (list of str)
      - short_summary (str)
      - summary (str alias)
      - recommendation (str)
    """
    # 1. Parse resume input
    candidate_skills: List[str] = []
    resume_text = ""

    if isinstance(resume, str):
        # Check if it is a JSON file path
        if resume.endswith(".json") and os.path.exists(resume):
            try:
                with open(resume, "r", encoding="utf-8") as f:
                    resume_data = json.load(f)
                candidate_skills = resume_data.get("skills", [])
                resume_text = resume_data.get("resume_text", "") or json.dumps(resume_data)
            except Exception as e:
                logger.warning("Failed to load resume JSON path: %s", e)
                resume_text = resume
        else:
            resume_text = resume
            candidate_skills = _extract_skills_from_text(resume_text)
    elif isinstance(resume, dict):
        candidate_skills = resume.get("skills", [])
        resume_text = resume.get("resume_text", "")
        if not candidate_skills and resume_text:
            candidate_skills = _extract_skills_from_text(resume_text)
        if not resume_text:
            resume_text = json.dumps(resume, indent=2)

    # 2. Parse job input
    jd_text = ""
    if isinstance(job, str):
        jd_text = job.strip()
    elif isinstance(job, dict):
        jd_text = job.get("description", "") or job.get("title", "") or json.dumps(job)

    if not jd_text:
        return {
            "match_score": 0,
            "matched_skills": [],
            "missing_skills": candidate_skills,
            "short_summary": "Empty job description provided.",
            "summary": "Empty job description provided.",
            "recommendation": "Skip",
        }

    # 3. AI Match Engine via LLM
    prompt = f"""You are an expert AI Technical Recruiter and Match Engine.
Compare the following candidate resume with the target job description.

Candidate Resume / Profile:
Skills: {json.dumps(candidate_skills)}
Details:
{resume_text[:2000]}

Target Job Description:
{jd_text[:2000]}

Analyze the match and return ONLY a valid JSON object in this exact schema:
{{
  "match_score": <integer from 0 to 100>,
  "matched_skills": [<skills from resume required or relevant to JD>],
  "missing_skills": [<critical skills/requirements in JD missing from candidate>],
  "short_summary": "<concise 2-3 sentence summary evaluating the candidate fit>"
}}
"""

    try:
        raw_response = LLM.generate(
            prompt=prompt,
            system="You evaluate candidate-job fit objectively and accurately. Return ONLY valid JSON."
        )

        clean_resp = raw_response.strip()
        if clean_resp.startswith("```json"):
            clean_resp = clean_resp[7:]
        if clean_resp.startswith("```"):
            clean_resp = clean_resp[3:]
        if clean_resp.endswith("```"):
            clean_resp = clean_resp[:-3]
        clean_resp = clean_resp.strip()

        data = json.loads(clean_resp)
        score = int(data.get("match_score", 0))
        score = max(0, min(100, score))
        matched = list(data.get("matched_skills", []))
        missing = list(data.get("missing_skills", []))
        short_summary = str(data.get("short_summary", "")).strip()

        recommendation = "Apply" if score >= 75 else ("Tailor Resume" if score >= 50 else "Skip")

        return {
            "match_score": score,
            "matched_skills": matched,
            "missing_skills": missing,
            "short_summary": short_summary,
            "summary": short_summary,
            "recommendation": recommendation,
        }
    except Exception as e:
        logger.info("LLM matching encountered an issue (%s), using deterministic fallback.", e)
        return _fallback_match(candidate_skills, resume_text, jd_text)
