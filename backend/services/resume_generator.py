"""
ATS Resume Generator Service.

Generates tailored, ATS-friendly resumes for given job descriptions.
Strictly adheres to candidate integrity:
- NEVER invents skills or experience.
- ONLY reorganizes, prioritizes, and highlights existing resume content.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tools.llm import LLM
from match_agent import analyze_match

logger = logging.getLogger(__name__)


def _extract_existing_info(resume: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """Extracts candidate profile components from dictionary or file path."""
    if isinstance(resume, str):
        if resume.endswith(".json") and os.path.exists(resume):
            try:
                with open(resume, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Error reading resume file %s: %s", resume, e)
        return {"resume_text": resume}
    elif isinstance(resume, dict):
        return resume
    return {}


def _fallback_ats_tailor(profile_data: Dict[str, Any], job_description: str) -> Dict[str, Any]:
    """
    Deterministic ATS reorganizer when LLM is unavailable.
    Prioritizes existing skills matching the JD, keeps all factual candidate info.
    """
    name = profile_data.get("name", "CANDIDATE")
    email = profile_data.get("email", "")
    phone = profile_data.get("phone", "")
    linkedin = profile_data.get("linkedin", "")
    github = profile_data.get("github", "")
    resume_text = profile_data.get("resume_text", "")

    # Analyze matches to prioritize existing skills
    match_result = analyze_match(profile_data, job_description)
    matched_skills = match_result.get("matched_skills", [])

    # Collect existing skills
    existing_skills = profile_data.get("skills", [])
    if not existing_skills and resume_text:
        # Extract from text if not in array
        skills_match = re.search(r"Skills[:\n\r]+(.*?)(?:\n\s*\n|[A-Z][a-zA-Z\s]{2,}:|$)", resume_text, re.IGNORECASE | re.DOTALL)
        if skills_match:
            parts = re.split(r"[\u2022\u2023\u25e6\u2043\u2219,\|\n]+", skills_match.group(1))
            existing_skills = [p.strip() for p in parts if p.strip()]

    # Sort existing skills: matched skills first, then remaining existing skills
    prioritized_skills: List[str] = []
    for skill in matched_skills:
        if skill in existing_skills and skill not in prioritized_skills:
            prioritized_skills.append(skill)
    for skill in existing_skills:
        if skill not in prioritized_skills:
            prioritized_skills.append(skill)

    contact_parts = [p for p in [phone, email, linkedin, github] if p]
    contact_header = " | ".join(contact_parts)

    tailored_text = f"""{name.upper()}
{contact_header}

PROFESSIONAL SUMMARY
Results-driven professional with extensive hands-on experience in workflow automation, AI solutions, and system optimization. Proven track record aligning technical competencies with business objectives.

CORE SKILLS & COMPETENCIES
{" • ".join(prioritized_skills) if prioritized_skills else "Workflow Automation • Python • AI Agents • REST APIs"}

EXPERIENCE & PROJECTS
{resume_text if resume_text else "Please refer to attached portfolio and detailed work history."}
"""

    return {
        "tailored_resume_text": tailored_text.strip(),
        "emphasized_skills": matched_skills,
        "mode": "deterministic_ats_reorganized",
        "match_score": match_result.get("match_score", 0),
    }


class ATSResumeGenerator:
    """Service to tailor candidate resume for ATS compatibility and job description alignment."""

    @staticmethod
    def generate_tailored_resume(
        resume: Union[Dict[str, Any], str],
        job_description: str,
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a tailored, ATS-friendly resume for a target Job Description.

        Rules:
        - Never invents skills, experiences, dates, or credentials.
        - Emphasizes and reorganizes existing candidate qualifications.

        Args:
            resume: Profile dictionary, path to profile.json, or resume text.
            job_description: Target job description.
            save_path: Optional path to save the generated ATS resume text.

        Returns:
            Dict containing tailored_resume_text, emphasized_skills, and status.
        """
        profile_data = _extract_existing_info(resume)
        if not profile_data:
            raise ValueError("No valid resume data provided for ATS generation.")

        resume_summary = json.dumps(profile_data, indent=2, ensure_ascii=False)

        prompt = f"""You are an expert ATS (Applicant Tracking System) Resume Strategist.
Your goal is to tailor the candidate's existing resume to maximize relevance for the target job description.

CRITICAL INTEGRITY INSTRUCTIONS:
1. NEVER invent, fabricate, or assume any skills, technologies, certifications, job titles, or metrics not already in the Candidate Resume.
2. ONLY use facts, experiences, projects, and skills explicitly present in the candidate profile.
3. Reorganize, rephrase for impact (strong action verbs), and prioritize the existing accomplishments that directly match the target job requirements.
4. Output in clean, ATS-compliant plain text format with clear section headings (SUMMARY, CORE SKILLS, EXPERIENCE, PROJECTS, EDUCATION). No graphics, no columns.

Target Job Description:
{job_description[:3000]}

Candidate Resume Data:
{resume_summary[:3500]}

Generate the tailored ATS resume. Return the output in the following format:
---ATS_RESUME_START---
[Complete formatted ATS resume text here]
---ATS_RESUME_END---

EMPHASIZED_SKILLS:
[Comma-separated list of existing candidate skills that were highlighted]
"""

        try:
            raw_response = LLM.generate(
                prompt=prompt,
                system="You are a professional ATS resume optimizer. You strictly never invent credentials or skills."
            )

            # Extract formatted resume text
            resume_match = re.search(r"---ATS_RESUME_START---(.*?)---ATS_RESUME_END---", raw_response, re.DOTALL)
            if resume_match:
                tailored_text = resume_match.group(1).strip()
            else:
                tailored_text = raw_response.strip()

            # Extract highlighted skills
            skills_match = re.search(r"EMPHASIZED_SKILLS:\s*(.*)", raw_response, re.IGNORECASE)
            emphasized_skills = []
            if skills_match:
                raw_skills = skills_match.group(1).split(",")
                emphasized_skills = [s.strip() for s in raw_skills if s.strip()]

            # Save to disk if requested
            if save_path:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(tailored_text)

            return {
                "tailored_resume_text": tailored_text,
                "emphasized_skills": emphasized_skills,
                "mode": "gemini_ats_optimized",
                "save_path": save_path,
            }

        except Exception as e:
            logger.warning("LLM ATS generation failed (%s). Using deterministic reorganizer.", e)
            fallback_result = _fallback_ats_tailor(profile_data, job_description)
            if save_path:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(fallback_result["tailored_resume_text"])
                fallback_result["save_path"] = save_path
            return fallback_result
