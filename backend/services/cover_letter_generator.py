"""
Cover Letter Generator Service.

Generates customized, persuasive cover letters based on candidate resume and Job Description.
Powered by Google Gemini with deterministic fallback.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from tools.llm import LLM
from match_agent import analyze_match

logger = logging.getLogger(__name__)


def _extract_profile(resume: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """Extract candidate profile dictionary from input."""
    if isinstance(resume, str):
        if resume.endswith(".json") and os.path.exists(resume):
            try:
                with open(resume, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Error reading profile %s: %s", resume, e)
        return {"resume_text": resume}
    elif isinstance(resume, dict):
        return resume
    return {}


def _infer_company_and_role(job_description: str) -> Dict[str, str]:
    """Infers company name and role title from JD if not explicitly provided."""
    role = ""
    company = ""

    role_match = re.search(r"(?:Role|Position|Title|Job Title)[:\s]+([^\n\r]+)", job_description, re.IGNORECASE)
    if role_match:
        role = role_match.group(1).strip()

    company_match = re.search(r"(?:Company|Organization|At)[:\s]+([^\n\r]+)", job_description, re.IGNORECASE)
    if company_match:
        company = company_match.group(1).strip()

    return {
        "role": role or "the advertised position",
        "company": company or "your organization"
    }


def _fallback_cover_letter(
    profile_data: Dict[str, Any],
    job_description: str,
    company_name: str,
    role_title: str
) -> Dict[str, Any]:
    """Deterministic fallback generator for cover letter."""
    name = profile_data.get("name", "Applicant")
    email = profile_data.get("email", "")
    phone = profile_data.get("phone", "")
    contact_line = " | ".join([p for p in [email, phone] if p])

    match_result = analyze_match(profile_data, job_description)
    matched_skills = match_result.get("matched_skills", [])
    skills_text = ", ".join(matched_skills[:4]) if matched_skills else "workflow automation, Python, and AI integrations"

    body = f"""{name}
{contact_line}

Dear Hiring Team at {company_name},

I am writing to express my strong enthusiasm for the {role_title} role at {company_name}. With my extensive background in operations combined with specialized hands-on expertise in {skills_text}, I am confident in my ability to make an immediate, positive impact on your team.

Throughout my career, I have designed and delivered scalable automation solutions, built AI agent workflows, and integrated enterprise APIs to eliminate inefficiencies and streamline complex operations. My practical experience aligning technical capabilities with real-world business demands enables me to understand requirements quickly and deploy reliable, measurable solutions.

What excites me most about {company_name} is the opportunity to contribute to high-impact challenges. My hands-on familiarity with {skills_text} positions me well to support your ongoing initiatives and drive engineering excellence.

Thank you for your time and consideration. I welcome the opportunity to discuss how my skill set and practical experience align with your goals for the {role_title} role.

Sincerely,

{name}
"""
    return {
        "cover_letter_text": body.strip(),
        "company_name": company_name,
        "role_title": role_title,
        "mode": "deterministic_fallback",
        "matched_skills": matched_skills,
    }


class CoverLetterGenerator:
    """Service to create personalized cover letters connecting resume to job requirements."""

    @staticmethod
    def generate(
        resume: Union[Dict[str, Any], str],
        job_description: str,
        company_name: Optional[str] = None,
        role_title: Optional[str] = None,
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a tailored cover letter using the candidate resume and Job Description.

        Args:
            resume: Candidate profile dict, path to profile.json, or resume text.
            job_description: Target job description.
            company_name: Optional explicit company name.
            role_title: Optional explicit role title.
            save_path: Optional path to save the generated cover letter text.

        Returns:
            Dict containing cover_letter_text, company_name, role_title, mode, save_path.
        """
        profile_data = _extract_profile(resume)
        if not profile_data:
            raise ValueError("No valid resume profile provided.")

        inferred = _infer_company_and_role(job_description)
        target_company = company_name or inferred["company"]
        target_role = role_title or inferred["role"]

        resume_context = json.dumps(profile_data, indent=2, ensure_ascii=False)

        prompt = f"""You are an executive career advisor and expert cover letter writer.
Write a compelling, authentic, and technically credible cover letter tailored specifically to the target job description.

GUIDELINES FOR AN AUTHENTIC, NON-CRAFTED HUMAN VOICE:
1. AUTHENTIC BUILDER TONE (AVOID AI CLICHÉS):
   - Sound like an experienced, thoughtful builder and technical operator speaking directly to another engineer or hiring manager.
   - ABSOLUTELY FORBIDDEN CLICHÉS: Do NOT start with "I am thrilled to apply...", "I am writing with great enthusiasm...", or "As a results-oriented professional...".
   - Open directly by highlighting immediate technical relevance and problem-solving readiness for {target_role} at {target_company}.
2. CONTEXTUAL & ORGANIC KEYWORD WEAVING:
   - Identify the primary domain and tooling required (e.g., GTM Engineering, Revenue Operations, Inbound/Outbound Automation, API & Webhook Integrations, LLM Orchestration, CRM sync).
   - Weave these concepts in naturally as functional solutions to the team's operational goals—never as a forced list of buzzwords.
3. GROUNDED STRICTLY IN TRUTH:
   - ONLY reference skills, technologies, and projects explicitly present in the candidate's actual profile. NEVER fabricate past titles, metrics, or company names.
4. TIGHT, COMPELLING STRUCTURE (3-4 PARAGRAPHS):
   - Professional Header with Candidate Name and contact info
   - Addressed to Hiring Team at {target_company}
   - Paragraph 1: Direct, punchy hook explaining exact technical fit and immediate value for {target_role}.
   - Paragraph 2: Tangible engineering/automation implementations (e.g., building autonomous job and email triage pipelines, integrating APIs, webhooks, CRM automation, LLM inference).
   - Paragraph 3: Alignment with {target_company}'s operational focus and why the candidate is excited to deliver real impact here.
   - Paragraph 4: Direct, professional closing call-to-action.
   - Professional sign-off

Target Company: {target_company}
Target Role: {target_role}

Target Job Description:
{job_description[:3000]}

Candidate Resume:
{resume_context[:3500]}

Output ONLY the final formatted cover letter text.
"""

        try:
            raw_letter = LLM.generate(
                prompt=prompt,
                system="You are an expert technical career strategist. Write concise, persuasive cover letters with an authentic human voice grounded strictly in candidate truth."
            )

            letter_text = raw_letter.strip()
            # Clean possible markdown wrapping
            if letter_text.startswith("```"):
                letter_text = re.sub(r"^```[a-zA-Z]*\n", "", letter_text)
                letter_text = re.sub(r"\n```$", "", letter_text)

            if save_path:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(letter_text)

            return {
                "cover_letter_text": letter_text,
                "company_name": target_company,
                "role_title": target_role,
                "mode": "gemini_generated",
                "save_path": save_path,
            }

        except Exception as e:
            logger.warning("LLM cover letter generation failed (%s). Using fallback template.", e)
            fallback_res = _fallback_cover_letter(profile_data, job_description, target_company, target_role)
            if save_path:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(fallback_res["cover_letter_text"])
                fallback_res["save_path"] = save_path
            return fallback_res
