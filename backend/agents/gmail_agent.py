"""
Gmail Agent Module.

Connects to Gmail via Google OAuth 2.0.
Monitors inbox for:
- Recruiter emails
- Job alerts
- Interview invitations
Extracts job descriptions and application links.
Automatically initiates the application workflow.

Powered by Google Gemini.
"""

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from tools.llm import LLM
from services.application_automator import ApplicationAutomator

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailAgent:
    """Agent for monitoring Gmail inbox, parsing recruiter/job alerts, and auto-applying."""

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json"
    ):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self._service = None

    def is_authenticated(self) -> bool:
        """Checks if a valid Google OAuth token is present."""
        if not self.token_path.exists():
            return False
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            return bool(creds and creds.valid)
        except Exception:
            return False

    def authenticate(self, port: int = 8080) -> bool:
        """
        Initiates Google OAuth 2.0 browser login flow and saves token.json.
        Requires credentials.json from Google Cloud Console.
        """
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception as e:
                logger.warning("Invalid token file: %s", e)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning("Token refresh failed: %s", e)
                    creds = None

            if not creds:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Missing {self.credentials_path}. Please download your OAuth client "
                        "credentials from Google Cloud Console and save as credentials.json."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=port)

            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        from googleapiclient.discovery import build
        self._service = build("gmail", "v1", credentials=creds)
        return True

    def _get_service(self):
        """Returns Gmail API service instance."""
        if not self._service:
            if not self.authenticate():
                raise RuntimeError("Failed to authenticate Gmail client.")
        return self._service

    @staticmethod
    def extract_links(text: str) -> List[str]:
        """Extracts potential job application URLs from message text."""
        url_pattern = r"https?://[^\s<>\"')]+"
        raw_urls = re.findall(url_pattern, text)
        filtered = []
        for u in raw_urls:
            domain = urlparse(u).netloc.lower()
            # Prioritize known job boards and career domains
            if any(ats in domain for ats in ["greenhouse.io", "lever.co", "ashbyhq.com", "workday", "smartrecruiters", "jobs", "careers"]):
                filtered.append(u)
            elif not any(ign in domain for ign in ["google.com", "gstatic.com", "unsubscribe", "linkedin.com/safety"]):
                filtered.append(u)
        return list(dict.fromkeys(filtered))[:5]

    @classmethod
    def analyze_email_content(cls, subject: str, sender: str, body: str) -> Dict[str, Any]:
        """
        Uses Gemini to classify the email and extract role, company, JD, and action items.
        """
        extracted_urls = cls.extract_links(body)

        prompt = f"""You are an expert AI Career and Email Parsing Agent.
Analyze this email and categorize it.

Sender: {sender}
Subject: {subject}
Body:
{body[:3000]}

Detected Links:
{json.dumps(extracted_urls)}

Classify the email into one of these exact categories:
- "recruiter_email" (A direct message or outreach from a recruiter/hiring manager)
- "job_alert" (A job posting notification or newsletter with open positions)
- "interview_invitation" (An interview schedule request, screening invite, or interview link)
- "other" (Rejection, marketing, or unrelated)

Return ONLY valid JSON matching this schema:
{{
  "category": "<recruiter_email | job_alert | interview_invitation | other>",
  "company_name": "<Inferred company name or Unknown>",
  "role_title": "<Inferred job position or Unknown>",
  "job_description_summary": "<Concise summary of role requirements and responsibilities, or null>",
  "is_actionable": <true if this contains a job opportunity to apply for or interview to respond to, else false>,
  "suggested_action": "<apply | reply | schedule | archive>",
  "extracted_apply_url": "<Best URL to apply, or null>"
}}
"""
        try:
            raw_response = LLM.generate(
                prompt=prompt,
                system="You are an expert recruitment email classifier. Return ONLY valid JSON."
            )
            clean_resp = raw_response.strip()
            if clean_resp.startswith("```json"):
                clean_resp = clean_resp[7:]
            if clean_resp.startswith("```"):
                clean_resp = clean_resp[3:]
            if clean_resp.endswith("```"):
                clean_resp = clean_resp[:-3]
            data = json.loads(clean_resp.strip())
        except Exception as e:
            logger.warning("LLM email classification failed (%s), using rule-based parsing.", e)
            category = "other"
            sub_lower = subject.lower()
            body_lower = body.lower()
            if "interview" in sub_lower or "interview" in body_lower:
                category = "interview_invitation"
            elif any(w in sub_lower for w in ["job", "role", "opening", "opportunity"]):
                category = "job_alert"
            elif any(w in body_lower for w in ["recruiter", "hiring manager", "found your profile"]):
                category = "recruiter_email"

            data = {
                "category": category,
                "company_name": "Unknown",
                "role_title": subject.split("-")[0].strip() if "-" in subject else subject[:30],
                "job_description_summary": body[:300],
                "is_actionable": category in ("recruiter_email", "job_alert", "interview_invitation"),
                "suggested_action": "apply" if extracted_urls else "reply",
                "extracted_apply_url": extracted_urls[0] if extracted_urls else None,
            }

        data["links_found"] = extracted_urls
        if not data.get("extracted_apply_url") and extracted_urls:
            data["extracted_apply_url"] = extracted_urls[0]

        return data

    def scan_inbox(self, max_results: int = 10, query: str = "recruiter OR interview OR 'job alert' OR opportunity") -> List[Dict[str, Any]]:
        """
        Scans Gmail inbox matching the query, analyzes content, and returns structured findings.
        """
        service = self._get_service()
        response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = response.get("messages", [])

        results = []
        for msg in messages:
            msg_id = msg["id"]
            try:
                full_msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                payload = full_msg.get("payload", {})
                headers = payload.get("headers", [])

                subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
                date = next((h["value"] for h in headers if h["name"].lower() == "date"), "")

                # Extract body text
                body = ""
                if "parts" in payload:
                    for part in payload["parts"]:
                        if part.get("mimeType") == "text/plain":
                            data = part.get("body", {}).get("data", "")
                            if data:
                                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                                break
                elif "body" in payload and payload["body"].get("data"):
                    body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

                analysis = self.analyze_email_content(subject=subject, sender=sender, body=body)

                results.append({
                    "id": msg_id,
                    "date": date,
                    "sender": sender,
                    "subject": subject,
                    **analysis
                })
            except Exception as e:
                logger.error("Error processing Gmail message %s: %s", msg_id, e)
                continue

        return results

    @classmethod
    def process_and_auto_apply(
        cls,
        email_data: Dict[str, Any],
        profile_path: str = "data/profile.json",
        headless: bool = True
    ) -> Dict[str, Any]:
        """
        Takes an analyzed email; if an apply link is present, triggers the Playwright Application Workflow.
        """
        apply_url = email_data.get("extracted_apply_url")
        if not apply_url:
            return {
                "status": "skipped",
                "message": "No application URL found in email.",
                "email_category": email_data.get("category"),
            }

        logger.info("Automatically launching Application Workflow for: %s", apply_url)
        app_result = ApplicationAutomator.apply_to_job(
            apply_url=apply_url,
            resume_profile=profile_path,
            headless=headless
        )

        return {
            "status": "workflow_started",
            "apply_url": apply_url,
            "company_name": email_data.get("company_name"),
            "role_title": email_data.get("role_title"),
            "application_result": app_result
        }
