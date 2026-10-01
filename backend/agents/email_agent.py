"""
Recruiter Email Generator Agent.

Detects recruiter/hiring manager email from Job Descriptions and drafts
targeted, professional outreach emails. If no email is detected, generates
a polished application draft.

Powered by Google Gemini with deterministic fallback.
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

# Common non-recruiter domains or addresses to filter out
GENERIC_FILTER_EMAILS = {
    "support@remoteok.com",
    "support@remoteok.io",
    "admin@remoteok.io",
    "noreply@remoteok.com",
    "privacy@company.com",
    "help@domain.com",
}


def _extract_profile_data(resume: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """Helper to extract profile dictionary from path or dict."""
    if isinstance(resume, str):
        if resume.endswith(".json") and os.path.exists(resume):
            try:
                with open(resume, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load profile %s: %s", resume, e)
        return {"resume_text": resume}
    elif isinstance(resume, dict):
        return resume
    return {}


def _extract_recruiter_email(text: str) -> Optional[str]:
    """Extracts first valid recruiter/company contact email from JD text."""
    if not text:
        return None
    matches = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    for email in matches:
        clean = email.strip().lower()
        if clean not in GENERIC_FILTER_EMAILS and not clean.startswith("noreply"):
            return email.strip()
    return None


def _infer_company_and_role(job_description: str) -> Dict[str, str]:
    """Infers company name and role title from JD."""
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
        "company": company or "your company"
    }


def _fallback_email(
    profile_data: Dict[str, Any],
    job_description: str,
    target_company: str,
    target_role: str,
    recipient_email: Optional[str]
) -> Dict[str, Any]:
    """Deterministic fallback email generator."""
    name = profile_data.get("name", "Applicant")
    email = profile_data.get("email", "")
    phone = profile_data.get("phone", "")
    linkedin = profile_data.get("linkedin", "")

    match_result = analyze_match(profile_data, job_description)
    matched_skills = match_result.get("matched_skills", [])
    skills_summary = ", ".join(matched_skills[:3]) if matched_skills else "Python, AI agents, and workflow automation"

    subject = f"Application: {target_role} - {name}"
    greeting = f"Dear {target_company} Hiring Team," if not recipient_email else f"Hello,"

    body = f"""{greeting}

I hope this email finds you well.

I am writing to apply for the {target_role} position at {target_company}. With my background in business operations combined with hands-on expertise in {skills_summary}, I am confident in my ability to deliver immediate value to your team.

Key highlights of my background include:
• Designing end-to-end automation workflows and AI solutions that eliminate operational bottlenecks.
• Hands-on technical experience with {skills_summary} and enterprise API integrations.
• A practical, results-driven approach to solving complex business challenges with modern AI tools.

I have attached my tailored resume and cover letter for your review. I would welcome the opportunity for a brief 10-15 minute conversation to discuss how my skill set can support {target_company}'s goals.

Thank you for your time and consideration.

Best regards,

{name}
{phone}
{email}
{linkedin}
""".strip()

    return {
        "subject": subject,
        "recipient_email": recipient_email or "[Recruiter Email]",
        "has_recruiter_email": bool(recipient_email),
        "body": body,
        "full_email": f"To: {recipient_email or '[Recruiter Email]'}\nSubject: {subject}\n\n{body}",
        "company_name": target_company,
        "role_title": target_role,
        "mode": "deterministic_fallback",
    }


class EmailAgent:
    """Agent that extracts recruiter contact information and crafts tailored outreach emails."""

    @staticmethod
    def generate_email(
        resume: Union[Dict[str, Any], str],
        job: Union[Dict[str, Any], str],
        company_name: Optional[str] = None,
        role_title: Optional[str] = None,
        recruiter_email: Optional[str] = None,
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a recruiter outreach email or application draft.

        Args:
            resume: Candidate profile dict, path to profile.json, or text.
            job: Job description string or job dict.
            company_name: Optional override company name.
            role_title: Optional override role title.
            recruiter_email: Optional explicit recruiter email.
            save_path: Optional file path to persist the email text.

        Returns:
            Dict containing subject, body, full_email, has_recruiter_email, recipient_email, mode.
        """
        profile_data = _extract_profile_data(resume)
        if not profile_data:
            raise ValueError("No valid resume profile provided.")

        jd_text = job if isinstance(job, str) else (job.get("description", "") or json.dumps(job))
        inferred = _infer_company_and_role(jd_text)
        target_company = company_name or (job.get("company") if isinstance(job, dict) else None) or inferred["company"]
        target_role = role_title or (job.get("title") if isinstance(job, dict) else None) or inferred["role"]

        # Detect recruiter email from input or JD text
        detected_email = recruiter_email or _extract_recruiter_email(jd_text)
        has_recruiter_email = bool(detected_email)

        candidate_name = profile_data.get("name", "Applicant")
        resume_summary = json.dumps(profile_data, indent=2, ensure_ascii=False)

        prompt = f"""You are an expert executive job search strategist.
Draft a concise, high-converting recruiter email for a job application.

Target Details:
Company: {target_company}
Role: {target_role}
Recruiter Email Detected: {"Yes (" + detected_email + ")" if detected_email else "No (prepare draft for hiring team)"}

Candidate Profile:
{resume_summary[:3500]}

Target Job Description:
{jd_text[:3000]}

CRITICAL RULES:
1. Keep the email concise (under 180 words). Recruiters skim emails in seconds.
2. NEVER invent skills, degrees, or metrics not in the Candidate Profile.
3. Highlight 2-3 genuine candidate strengths that directly answer the JD requirements.
4. Professional, confident, and direct tone with clear call-to-action.
5. Provide ONLY valid JSON with this exact schema:
{{
  "subject": "<Compelling subject line with candidate name and role>",
  "body": "<Complete email body including greeting, concise bulleted value prop, and sign-off>"
}}
"""

        try:
            raw_response = LLM.generate(
                prompt=prompt,
                system="You are an expert recruiter and career strategist. Return ONLY valid JSON."
            )

            clean_resp = raw_response.strip()
            if clean_resp.startswith("```json"):
                clean_resp = clean_resp[7:]
            if clean_resp.startswith("```"):
                clean_resp = clean_resp[3:]
            if clean_resp.endswith("```"):
                clean_resp = clean_resp[:-3]
            clean_resp = clean_resp.strip()

            parsed = json.loads(clean_resp)
            subject = str(parsed.get("subject", f"Application: {target_role} - {candidate_name}")).strip()
            body = str(parsed.get("body", "")).strip()

            full_email = f"To: {detected_email or '[Recruiter / Hiring Team Email]'}\nSubject: {subject}\n\n{body}"

            if save_path:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(full_email)

            return {
                "subject": subject,
                "body": body,
                "full_email": full_email,
                "has_recruiter_email": has_recruiter_email,
                "recipient_email": detected_email or "[Recruiter Email]",
                "company_name": target_company,
                "role_title": target_role,
                "mode": "gemini_generated",
                "save_path": save_path,
            }

        except Exception as e:
            logger.warning("LLM email generation error (%s). Using fallback template.", e)
            fallback = _fallback_email(profile_data, jd_text, target_company, target_role, detected_email)
            if save_path:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(fallback["full_email"])
                fallback["save_path"] = save_path
            return fallback
