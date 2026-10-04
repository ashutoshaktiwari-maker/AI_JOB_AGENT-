"""
Gmail Job Reader Service for Keyword Email Ingestion.

1. Connects to Gmail via Google OAuth 2.0 (backend/credentials.json & backend/token.json)
   using scopes:
   - https://www.googleapis.com/auth/gmail.readonly
   - https://www.googleapis.com/auth/gmail.modify
2. Scans unread emails matching keyword search queries:
   is:unread ("Python AI" OR "AI Agent" OR "remote" ...)
3. Extracts sender, subject, body text, detected recruiter email address, and apply URLs.
4. Identifies interview/screening invitations with is_interview flag.
5. Automatically marks processed emails as READ to prevent duplicate alerts.
"""

import base64
import email.utils
import html
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Official Gmail OAuth 2.0 Scopes required
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Interview detection patterns
INTERVIEW_PATTERNS = [
    r"\binterview\b",
    r"\bscreening\b",
    r"\binvitation\b",
    r"\bschedule\s+a\s+call\b",
    r"\bnext\s+steps\b",
    r"\bcalendly\.com\b",
]

# Domains typically representing automated notifications rather than direct human recruiters
GENERIC_DOMAINS = [
    "no-reply",
    "noreply",
    "notifications",
    "mailer-daemon",
    "alerts",
    "donotreply",
    "automated",
    "bounce",
]

# ATS & Career board URL domains to prioritize
ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "taleo.net",
    "smartrecruiters.com",
    "workable.com",
    "apply",
    "careers",
    "jobs",
    "calendly.com",
]


def resolve_oauth_paths() -> tuple[Path, Path]:
    """
    Locates backend/credentials.json and backend/token.json flexibly.
    Checks backend/ and current working directory.
    """
    backend_dir = Path(__file__).resolve().parent.parent

    creds_candidates = [
        backend_dir / "credentials.json",
        Path("backend/credentials.json"),
        Path("credentials.json"),
    ]
    token_candidates = [
        backend_dir / "token.json",
        Path("backend/token.json"),
        Path("token.json"),
    ]

    creds_path = next((c for c in creds_candidates if c.exists()), backend_dir / "credentials.json")
    token_path = next((t for t in token_candidates if t.exists()), backend_dir / "token.json")
    return creds_path, token_path


def clean_html(raw_html: str) -> str:
    """Strips HTML tags and normalizes whitespace."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(raw_html))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class GmailJobReader:
    """Service for authenticating with Gmail API and ingesting job-related emails."""

    def __init__(
        self,
        credentials_path: Optional[Path | str] = None,
        token_path: Optional[Path | str] = None,
    ):
        def_creds, def_token = resolve_oauth_paths()
        self.credentials_path = Path(credentials_path) if credentials_path else def_creds
        self.token_path = Path(token_path) if token_path else def_token
        self._service: Any = None

    def is_authenticated(self) -> bool:
        """Checks if a valid Google OAuth token is present."""
        if not self.token_path.exists():
            return False
        try:
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            return bool(creds and (creds.valid or (creds.expired and creds.refresh_token)))
        except Exception as e:
            logger.debug("Token check exception: %s", e)
            return False

    def get_service(self, interactive_port: int = 8080) -> Any:
        """
        Initializes and returns the Google Gmail API service.
        Refreshes expired credentials if refresh_token is present.
        Launches local server OAuth flow if credentials.json exists and no token is saved.
        """
        if self._service:
            return self._service

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception as e:
                logger.warning("Could not load token file %s: %s", self.token_path, e)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning("Failed refreshing token: %s", e)
                    creds = None

            if not creds:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Missing Gmail OAuth credentials file: {self.credentials_path}. "
                        "Please download OAuth client credentials from Google Cloud Console "
                        "and place at backend/credentials.json."
                    )
                from google_auth_oauthlib.flow import InstalledAppFlow

                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=interactive_port)

            # Persist updated token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    @staticmethod
    def build_search_query(keywords: List[str]) -> str:
        """
        Builds Gmail search query string:
        is:unread ("Python AI" OR "AI Agent" OR "remote" ...)
        """
        cleaned_kws = [k.strip() for k in keywords if k and k.strip()]
        if not cleaned_kws:
            return "is:unread"

        parts = []
        for kw in cleaned_kws:
            # Quote if contains whitespace or multiple words
            if " " in kw:
                parts.append(f'"{kw}"')
            else:
                parts.append(f'"{kw}"')
        joined = " OR ".join(parts)
        return f"is:unread ({joined})"

    @classmethod
    def extract_body(cls, payload: Dict[str, Any]) -> str:
        """
        Recursively extracts plaintext body from message payload parts.
        Falls back to stripped text/html if plaintext is absent.
        """
        if not payload:
            return ""

        text_plain_parts: List[str] = []
        text_html_parts: List[str] = []

        def _traverse_parts(parts: List[Dict[str, Any]]) -> None:
            for part in parts:
                mime_type = part.get("mimeType", "")
                sub_parts = part.get("parts")
                if sub_parts:
                    _traverse_parts(sub_parts)

                body_data = part.get("body", {}).get("data")
                if body_data:
                    try:
                        decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                        if mime_type == "text/plain":
                            text_plain_parts.append(decoded)
                        elif mime_type == "text/html":
                            text_html_parts.append(clean_html(decoded))
                    except Exception as e:
                        logger.debug("Failed decoding body part: %s", e)

        # Check top-level parts or root body
        if "parts" in payload:
            _traverse_parts(payload["parts"])
        elif "body" in payload and payload["body"].get("data"):
            try:
                decoded = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
                mime = payload.get("mimeType", "")
                if mime == "text/html":
                    return clean_html(decoded)
                return decoded
            except Exception as e:
                logger.debug("Failed decoding top-level body: %s", e)

        if text_plain_parts:
            return "\n\n".join(text_plain_parts).strip()
        if text_html_parts:
            return "\n\n".join(text_html_parts).strip()
        return ""

    @staticmethod
    def detect_recruiter_email(sender: str, body: str) -> Optional[str]:
        """
        Detects recruiter email address from From header or body text.
        Prioritizes direct human emails over automated notification bots.
        """
        _, sender_addr = email.utils.parseaddr(sender or "")
        sender_addr = sender_addr.strip().lower()

        is_sender_generic = any(gen in sender_addr for gen in GENERIC_DOMAINS)

        # 1. Search body for explicit recruiter contact patterns
        recruiter_patterns = [
            r"(?:reach\s+out\s+to|contact(?:\s+me)?(?:\s+at)?|email(?:\s+me)?(?:\s+at)?|write\s+to|recruiter:?)\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
            r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\s+(?:is\s+the\s+recruiter|from\s+talent\s+acquisition)",
        ]
        for pat in recruiter_patterns:
            matches = re.findall(pat, body, re.IGNORECASE)
            for m in matches:
                candidate = m.strip().lower()
                if not any(gen in candidate for gen in GENERIC_DOMAINS):
                    return candidate

        # 2. If sender is not an automated no-reply bot, sender is the recruiter
        if sender_addr and not is_sender_generic:
            return sender_addr

        # 3. Fallback: find any valid email in body that is not a generic domain
        all_emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", body)
        for em in all_emails:
            clean_em = em.strip().lower()
            if not any(gen in clean_em for gen in GENERIC_DOMAINS):
                return clean_em

        return sender_addr if sender_addr else None

    @staticmethod
    def extract_apply_urls(body: str) -> List[str]:
        """
        Extracts application and job posting URLs from body text.
        Sorts known ATS and job boards to the front.
        """
        if not body:
            return []
        raw_urls = re.findall(r"https?://[^\s<>\"')]+", body)
        valid_urls: List[str] = []

        for u in raw_urls:
            cleaned = u.rstrip(".,;:!?)'\"")
            domain = urlparse(cleaned).netloc.lower()
            # Skip noise / unsubscribe / image assets
            if any(ign in domain for ign in ["google.com", "gstatic.com", "unsubscribe", "schema.org", "w3.org"]):
                continue
            if cleaned not in valid_urls:
                valid_urls.append(cleaned)

        # Prioritize known ATS / career portals
        sorted_urls = sorted(
            valid_urls,
            key=lambda link: 0 if any(ats in link.lower() for ats in ATS_DOMAINS) else 1,
        )
        return sorted_urls

    @staticmethod
    def is_interview_email(subject: str, body: str) -> bool:
        """
        Evaluates whether an email represents an interview invitation, screening request,
        or scheduling opportunity.
        """
        text = f"{subject or ''} {body or ''}".lower()
        return any(re.search(pat, text, re.IGNORECASE) for pat in INTERVIEW_PATTERNS)

    @classmethod
    def mark_as_read(cls, service: Any, message_id: str) -> bool:
        """
        Marks an email as READ in Gmail by removing the UNREAD label.
        Prevents duplicate alerts.
        """
        try:
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            logger.info("Marked Gmail message %s as READ.", message_id)
            return True
        except Exception as e:
            logger.warning("Failed to mark Gmail message %s as read: %s", message_id, e)
            return False

    def scan_job_emails(
        self,
        keywords: List[str],
        max_results: int = 50,
        mark_read: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Scans unread emails matching keywords query:
        is:unread ("Python AI" OR "AI Agent" OR "remote" ...)
        Extracts sender, subject, body text, detected recruiter email address, and apply URLs.
        Flags is_interview: True if interview/screening words are detected.
        Marks processed emails as READ to prevent duplicate alerts.
        """
        service = self.get_service()
        query = self.build_search_query(keywords)
        logger.info("Querying Gmail with: %s", query)

        try:
            response = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()
        except Exception as e:
            logger.error("Gmail list messages query failed: %s", e)
            return []

        message_summaries = response.get("messages", [])
        extracted_emails: List[Dict[str, Any]] = []

        for item in message_summaries:
            msg_id = item.get("id")
            if not msg_id:
                continue

            try:
                full_msg = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="full",
                ).execute()

                payload = full_msg.get("payload", {})
                headers = payload.get("headers", [])

                subject = next(
                    (h["value"] for h in headers if h.get("name", "").lower() == "subject"),
                    "No Subject",
                )
                sender = next(
                    (h["value"] for h in headers if h.get("name", "").lower() == "from"),
                    "Unknown Sender",
                )
                date_str = next(
                    (h["value"] for h in headers if h.get("name", "").lower() == "date"),
                    "",
                )

                body_text = self.extract_body(payload)
                recruiter_email = self.detect_recruiter_email(sender, body_text)
                apply_urls = self.extract_apply_urls(body_text)
                is_interview = self.is_interview_email(subject, body_text)

                email_record = {
                    "id": str(msg_id),
                    "sender": str(sender),
                    "subject": str(subject),
                    "body": str(body_text),
                    "recruiter_email": recruiter_email,
                    "apply_urls": apply_urls,
                    "is_interview": is_interview,
                    "date": str(date_str),
                }

                extracted_emails.append(email_record)

                # Mark processed email as READ to prevent duplicate alerts
                if mark_read:
                    self.mark_as_read(service, msg_id)

            except Exception as exc:
                logger.error("Error processing Gmail message %s: %s", msg_id, exc)
                continue

        logger.info(
            "Completed Gmail scan: ingested %d emails (%d interviews detected).",
            len(extracted_emails),
            sum(1 for e in extracted_emails if e.get("is_interview")),
        )
        return extracted_emails


# Standalone function conforming to the exact requirement
def scan_job_emails(keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Scans unread emails matching keyword query, extracts sender, subject,
    body text, recruiter email, and apply URLs, flags interviews, and marks as READ.
    """
    reader = GmailJobReader()
    return reader.scan_job_emails(keywords=keywords, mark_read=True)
