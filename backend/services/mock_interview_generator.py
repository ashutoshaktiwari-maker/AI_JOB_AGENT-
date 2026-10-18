"""
Mock Interview Question Generator Service.

Generates 10 tailored mock interview practice questions with key answer guidance
whenever an interview invitation is detected for a candidate.
Grounded in target role, company domain, and candidate engineering background.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.llm import LLM

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INTERVIEW_PREP_DIR = DATA_DIR / "interview_prep"


def _sanitize_filename(text: str) -> str:
    """Creates a filesystem-safe filename slug."""
    clean = re.sub(r"[^\w\s-]", "", str(text or "")).strip().lower()
    return re.sub(r"[-\s]+", "_", clean)[:40] or "interview"


def _fallback_mock_questions(company: str, role: str) -> Dict[str, Any]:
    """Deterministic fallback mock questions when LLM is unavailable."""
    comp = company or "the company"
    r = role or "Automation / AI Engineer"

    questions = [
        f"1. [Architecture] How would you design an end-to-end webhook-based integration between a CRM (like HubSpot or Salesforce) and a data pipeline at {comp} to ensure zero data loss during high throughput?",
        f"2. [Technical] In Python, how do you handle idempotency and API rate limits when orchestrating multiple third-party REST APIs?",
        f"3. [AI / LLMs] How would you evaluate and optimize prompt latency and hallucination risks when using LLM APIs (OpenAI/Gemini/Claude) for customer lead qualification?",
        f"4. [Workflow] Describe an automation pipeline you built using n8n or Make.com. What unexpected failure mode did you encounter and how did you resolve it?",
        f"5. [Error Handling] If an upstream webhook payload suddenly changes its JSON schema without notice, how would your ingestion service detect and gracefully alert on the discrepancy?",
        f"6. [Data Pipeline] How do you structure data validation and transformation when syncing lead enrichment data from engines like Clay or Apollo into operational databases?",
        f"7. [Production Scenario] Walk us through how you would diagnose a silent failure where an automated workflow succeeds with a 200 OK status code but delivers empty or corrupt records.",
        f"8. [Business Impact] How do you communicate technical pipeline constraints and delivery timelines to non-technical stakeholders (e.g., Sales or Marketing leadership)?",
        f"9. [Company Alignment] Looking at {comp}'s product and operations, what is one business process you believe could be immediately accelerated with an AI automation pipeline?",
        f"10. [Role Vision] What excites you most about stepping into the {r} role at {comp}, and how do you plan to create impact in your first 30 days?",
    ]

    telegram_summary = (
        f"🎯 *10 Mock Interview Questions for Practice*\n"
        f"🏢 *Company:* {comp} | 💼 *Role:* {r}\n\n"
        + "\n\n".join(questions)
        + "\n\n💡 _Full prep guide saved locally in backend/data/interview_prep/_"
    )

    return {
        "company": comp,
        "role": r,
        "questions": questions,
        "telegram_text": telegram_summary,
        "full_text": "\n\n".join(questions),
        "mode": "deterministic_fallback",
    }


class MockInterviewGenerator:
    """Generates 10 targeted mock interview questions for candidate practice."""

    @classmethod
    def generate_questions(
        cls,
        company: str,
        role: str,
        snippet: str = "",
        save: bool = True,
    ) -> Dict[str, Any]:
        """
        Generates 10 tailored mock interview questions with answers/talking points.
        Saves questions to backend/data/interview_prep/ and returns formatted dict.
        """
        target_company = (company or "Hiring Company").strip()
        target_role = (role or "Target Role").strip()
        details_context = (snippet or "").strip()[:1500]

        prompt = f"""You are a Principal Hiring Manager and Elite Technical Interviewer.
The candidate has received an interview invitation for:
Company: {target_company}
Role: {target_role}

Email / Job Snippet Context:
{details_context}

Generate exactly 10 high-impact, realistic mock interview questions tailored specifically for this interview.
Structure the 10 questions across these categories:
- Questions 1-3: Technical Architecture & Core Stack (Python, REST APIs, Webhooks, LLM pipelines, CRM/Data sync)
- Questions 4-6: Workflow Orchestration & Systems Resilience (Rate limits, retry logic, error handling, automation pipelines)
- Questions 7-8: Production Debugging & Operational Scenarios (Diagnosing silent failures, cross-functional collaboration)
- Questions 9-10: Company-Specific Alignment & Role Impact (Why this company, 30-day impact plan)

For EACH question:
- Clearly state the Question.
- Include a 1-2 sentence "Key Talking Point" advising the candidate on what the interviewer is looking for.

Format each item cleanly as:
Q1. [Category] Question text here?
Key Point: What to emphasize in your answer.

Be direct, highly professional, and relevant to modern AI, Automation, and GTM systems.
"""

        try:
            raw_response = LLM.generate(
                prompt=prompt,
                system="You are an elite technical interviewer. Generate realistic, high-impact mock interview questions with practical answer guidance."
            )
            cleaned_text = raw_response.strip()

            # Build Telegram-friendly summary (concise preview)
            lines = [l.strip() for l in cleaned_text.split("\n") if l.strip()]
            q_lines = [l for l in lines if re.match(r"^Q\d+[\.:\s]", l, re.I) or re.match(r"^\d+[\.:\s]", l)]

            if len(q_lines) >= 10:
                preview_list = q_lines[:10]
            elif len(q_lines) >= 1:
                preview_list = q_lines
            else:
                preview_list = lines[:15]

            joined_qs = "\n\n".join(preview_list)
            if len(joined_qs) > 2800:
                joined_qs = joined_qs[:2800] + "\n...(truncated for Telegram)"

            telegram_summary = (
                f"🎯 *10 MOCK INTERVIEW QUESTIONS FOR PRACTICE*\n"
                f"🏢 *Company:* {target_company} | 💼 *Role:* {target_role}\n\n"
                + joined_qs
                + f"\n\n💡 _Full prep guide with talking points saved locally in backend/data/interview_prep/_"
            )

            result = {
                "company": target_company,
                "role": target_role,
                "full_text": cleaned_text,
                "telegram_text": telegram_summary,
                "mode": "gemini_generated",
            }

        except Exception as exc:
            logger.warning("LLM mock interview generation failed (%s). Using fallback.", exc)
            result = _fallback_mock_questions(target_company, target_role)

        # Save to disk
        if save:
            INTERVIEW_PREP_DIR.mkdir(parents=True, exist_ok=True)
            slug = f"{_sanitize_filename(target_company)}_{_sanitize_filename(target_role)}"
            out_file = INTERVIEW_PREP_DIR / f"{slug}_mock_interview.txt"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(f"MOCK INTERVIEW PREPARATION GUIDE\n")
                f.write(f"Company: {target_company}\n")
                f.write(f"Role: {target_role}\n")
                f.write(f"=" * 60 + "\n\n")
                f.write(result["full_text"])
            result["file_path"] = str(out_file)
            logger.info("Saved mock interview questions to %s", out_file)

        return result
