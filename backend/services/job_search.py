"""Zero-login Job Search Service for GTM Engineering & Revenue Automation."""

import html
import logging
import re
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)
REQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 1. Target Roles & Deduplicated Search Keywords
TARGET_ROLES = ["GTM Engineer", "Revenue Operations Automation", "Marketing Automation Engineer", "Growth Engineer"]
SEARCH_KEYWORDS = ["GTM Engineer", "Revenue Operations", "Marketing Automation", "Growth Engineer", "RevOps Automation", "Inbound Automation"]

# 2. Core Skills & Tooling Taxonomy
CORE_SKILLS_TAXONOMY = {
    "Enrichment & Outbound Engines": ["Clay", "Apollo.io", "ZoomInfo", "Clearbit"],
    "CRM & Marketing Automation": ["HubSpot", "Salesforce", "Marketo", "Customer.io"],
    "Cold Outreach & Email Deliverability": ["Instantly.ai", "Smartlead", "Lemlist"],
    "Workflow & Integration Automation": ["Zapier", "Make", "n8n", "Webhooks", "REST APIs"],
    "Modern Stack": ["Python", "SQL", "Playwright", "LLM orchestration", "OpenAI API", "Gemini API"],
}

# 3. Public Ingestion Boards (Strictly Zero-Login)
BOARDS_CONFIG = {
    "greenhouse": ["hubspot", "segment", "zapier", "postman", "gitlab", "faire", "canonical", "upstart", "block", "remote", "cloudbeds", "bold", "upwork"],
    "ashby": ["clay", "apollo", "customerio", "replit", "linear", "deel", "quantum", "patreon", "oyster", "supabase", "notion", "float", "1password", "hinge-health", "hubstaff", "hex", "constructor", "miro", "buffer"],
    "lever": ["lemlist", "buffer", "kinsta", "articulate", "verygoodsecurity"],
}

LOCATION_ALLOW = ("india", "worldwide", "anywhere", "global", "apac", "remote")
EXCLUDE_PATTERNS = [
    r"\bus\s+citizen\b", r"\bw2\s+only\b", r"\bus\s*/\s*eu\s+only\b", r"\bc2c\b",
    r"\bmust\s+reside\s+in\s+(?:the\s+)?us\b", r"\bus\s+only\b", r"\buk\s+only\b", r"\bcanada\s+only\b"
]
FRICTION_ATS = ("myworkdayjobs.com", "taleo.net", "icims.com")
SENIOR_PATTERN = r"\b(?:sr\.?|senior)\b"


def is_senior_role(title: str = "") -> bool:
    if not title: return False
    return bool(re.search(SENIOR_PATTERN, title, flags=re.I))


def clean_html(raw_html: Optional[str]) -> str:
    if not raw_html: return ""
    text = re.sub(r"<(?:br|p|div|li)[^>]*>", " ", html.unescape(str(raw_html)), flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def is_eligible_for_india(location: str = "", description: str = "", url: str = "", title: str = "", **kwargs: Any) -> bool:
    all_texts = [str(x or "") for x in [location, description, url, title] + list(kwargs.values())]
    full = " ".join(all_texts).lower()
    if any(ats in full for ats in FRICTION_ATS) or any(re.search(pat, full) for pat in EXCLUDE_PATTERNS):
        return False
    loc = (location or "").lower()
    if not any(t in loc for t in LOCATION_ALLOW) and not any(t in full for t in LOCATION_ALLOW):
        return False
    return any(t in full for t in LOCATION_ALLOW)


def normalize_job(id_: Any, title: str, company: str, url: str, location: str, description: str, portal: str) -> Dict[str, str]:
    return {
        "id": str(id_).strip(), "title": str(title).strip(), "company": str(company).strip(),
        "url": str(url).strip(), "location": str(location).strip() or "Remote",
        "description": clean_html(description), "portal": str(portal).strip()
    }


class JobSearchService:
    @staticmethod
    def _fetch_greenhouse_board(company: str, slug: str) -> List[Dict[str, str]]:
        try:
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", headers=REQ_HEADERS, timeout=8)
            if r.status_code != 200: return []
            jobs = []
            for j in r.json().get("jobs", []):
                t = j.get("title", "")
                if is_senior_role(t): continue
                loc, u, desc = (j.get("location") or {}).get("name", "Remote"), j.get("absolute_url", ""), j.get("content", "")
                if is_eligible_for_india(location=loc, description=desc, url=u, title=t):
                    jobs.append(normalize_job(j.get("id", ""), t, company, u, loc, desc, f"Greenhouse ({company})"))
            return jobs
        except Exception:
            return []

    @staticmethod
    def _fetch_ashby_board(company: str, slug: str) -> List[Dict[str, str]]:
        try:
            r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", headers=REQ_HEADERS, timeout=8)
            if r.status_code != 200: return []
            jobs = []
            for j in r.json().get("jobs", []):
                t = j.get("title", "")
                if is_senior_role(t): continue
                loc, u = j.get("location") or "Remote", j.get("jobUrl", "")
                desc = j.get("descriptionPlain") or j.get("descriptionHtml") or ""
                if is_eligible_for_india(location=loc, description=desc, url=u, title=t):
                    jobs.append(normalize_job(j.get("id", ""), t, company, u, loc, desc, f"Ashby ({company})"))
            return jobs
        except Exception:
            return []

    @staticmethod
    def _fetch_lever_board(company: str, slug: str) -> List[Dict[str, str]]:
        try:
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=REQ_HEADERS, timeout=8)
            if r.status_code != 200: return []
            jobs = []
            for j in r.json():
                t = j.get("text", "")
                if is_senior_role(t): continue
                loc = (j.get("categories") or {}).get("location", "Remote")
                u, desc = j.get("hostedUrl", ""), j.get("descriptionPlain") or j.get("description", "")
                if is_eligible_for_india(location=loc, description=desc, url=u, title=t):
                    jobs.append(normalize_job(j.get("id", ""), t, company, u, loc, desc, f"Lever ({company})"))
            return jobs
        except Exception:
            return []

    @staticmethod
    def fetch_jobicy(tag: str = "marketing") -> List[Dict[str, str]]:
        try:
            r = requests.get(f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}", headers=REQ_HEADERS, timeout=8)
            if r.status_code != 200: return []
            jobs = []
            for j in r.json().get("jobs", []):
                t = j.get("jobTitle", "")
                if is_senior_role(t): continue
                loc, u, desc = j.get("jobGeo", "Remote"), j.get("url", ""), j.get("jobDescription", "")
                if is_eligible_for_india(location=loc, description=desc, url=u, title=t):
                    jobs.append(normalize_job(j.get("id", ""), t, j.get("companyName", "Jobicy"), u, loc, desc, "Jobicy"))
            return jobs
        except Exception:
            return []

    @staticmethod
    def fetch_remotive(category: str = "marketing") -> List[Dict[str, str]]:
        try:
            r = requests.get(f"https://remotive.com/api/remote-jobs?category={category}", headers=REQ_HEADERS, timeout=8)
            if r.status_code != 200: return []
            jobs = []
            for j in r.json().get("jobs", []):
                t = j.get("title", "")
                if is_senior_role(t): continue
                loc, u, desc = j.get("candidate_required_location", "Remote"), j.get("url", ""), j.get("description", "")
                if is_eligible_for_india(location=loc, description=desc, url=u, title=t):
                    jobs.append(normalize_job(j.get("id", ""), t, j.get("company_name", "Remotive"), u, loc, desc, "Remotive"))
            return jobs
        except Exception:
            return []

    fetch_himalayas = fetch_weworkremotely = staticmethod(lambda *a, **k: [])

    @classmethod
    def fetch_all_sources(cls) -> List[Dict[str, str]]:
        all_jobs: List[Dict[str, str]] = []
        for b in BOARDS_CONFIG["greenhouse"]: all_jobs.extend(cls._fetch_greenhouse_board(b.title(), b))
        for b in BOARDS_CONFIG["ashby"]: all_jobs.extend(cls._fetch_ashby_board(b.title(), b))
        for b in BOARDS_CONFIG["lever"]: all_jobs.extend(cls._fetch_lever_board(b.title(), b))
        all_jobs.extend(cls.fetch_jobicy(tag="marketing"))
        all_jobs.extend(cls.fetch_remotive(category="marketing"))
        return all_jobs

    @classmethod
    def search(cls, keyword: str = "", portal: str = "All Sources", max_total: int = 50) -> List[Dict[str, str]]:
        jobs, kw = cls.fetch_all_sources(), keyword.lower().strip()
        matched, seen = [], set()
        for j in jobs:
            if is_senior_role(j.get("title", "")): continue
            text = f"{j['title']} {j['description']}".lower()
            if (not kw or kw in text) and j["url"].lower() not in seen:
                seen.add(j["url"].lower())
                matched.append(j)
                if len(matched) >= max_total: break
        return matched


class ZeroLoginJobFetcher:
    """Zero-login multi-keyword job fetcher for GTM & Automation roles."""

    @classmethod
    def get_all_jobs(cls, keywords: Optional[List[str]] = None, max_per_kw: int = 25) -> List[Dict[str, str]]:
        target_kws = keywords or SEARCH_KEYWORDS
        all_jobs = JobSearchService.fetch_all_sources()
        res, seen = [], set()
        for kw in target_kws:
            kw_l, kw_count = kw.lower().strip(), 0
            for j in all_jobs:
                if is_senior_role(j.get("title", "")): continue
                u = j["url"].lower()
                if (not kw_l or kw_l in f"{j['title']} {j['description']}".lower()) and u not in seen:
                    seen.add(u)
                    res.append(j)
                    kw_count += 1
                    if kw_count >= max_per_kw: break
        return res
