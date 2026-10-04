"""
Unified Zero-Login Multi-Source Job Search & Target Company Scraper.

Ingests job postings from endpoints requiring NO user authentication or registration:
1. Greenhouse Public APIs:
   gitlab, canonical, automattic, duckduckgo, wikimedia, remotecom, postman, elastic, cockroachlabs, github
   Endpoint: https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true
2. Ashby Public APIs:
   supabase, zapier, deel, openai, replit, linear, anysphere
   Endpoint: https://api.ashbyhq.com/posting-api/job-board/{company}
3. Lever Public APIs:
   palantir, kinsta, buffer, auth0
   Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
4. Public Aggregator APIs:
   - Jobicy: https://jobicy.com/api/v2/remote-jobs?count=50&geo=apac
   - Remotive: https://remotive.com/api/remote-jobs?search={keyword}
   - RemoteOK: https://remoteok.com/api?tag={keyword}
   - Himalayas: https://himalayas.app/jobs/api?country=India
   - Arbeitnow: https://www.arbeitnow.com/api/job-board-api
5. RSS Feeds:
   - WeWorkRemotely: https://weworkremotely.com/categories/remote-programming-jobs.rss
   - Dev.to: https://dev.to/feed/tag/jobs

Applies strict filtering for India remote candidates:
- ALLOW if location or body includes: "india", "worldwide", "anywhere", "global", "apac", "remote".
- REJECT if description contains: "us citizen", "w2 only", "us/eu only", "c2c", "must reside in us", "us only", "uk only", "canada only".
- REJECT legacy friction ATS URLs: skip links with "myworkdayjobs.com" or "taleo.net".

Normalizes every job dictionary to:
{"id": str, "title": str, "company": str, "url": str, "location": str, "description": str, "portal": str}
"""

import hashlib
import html
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
import feedparser
import requests

logger = logging.getLogger(__name__)

# In-memory cache: {cache_key: (timestamp, [jobs])}
_IN_MEMORY_CACHE: Dict[str, tuple[float, List[Dict[str, str]]]] = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 600  # 10 minutes cache

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/xml, */*",
}
DEFAULT_TIMEOUT = 8  # seconds

# ---------------- FILTERING RULES ----------------

ALLOW_TERMS = [
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune",
    "gurgaon", "gurugram", "noida", "chennai", "kolkata", "ahmedabad",
    "worldwide", "anywhere", "global", "apac", "asia", "remote"
]

EXCLUDE_PATTERNS = [
    r"\bus\s+citizen(?:s)?\b",
    r"\bu\.s\.\s+citizen(?:s)?\b",
    r"\bw2\s+only\b",
    r"\bus\s*/\s*eu\s+only\b",
    r"\bus\s+only\b",
    r"\bu\.s\.\s+only\b",
    r"\bc2c\b",
    r"\bcorp(?:orate)?\s+to\s+corp(?:orate)?\b",
    r"\bmust\s+reside\s+in\s+(?:the\s+)?(?:us|u\.s\.|usa|united\s+states|uk|u\.k\.|canada)\b",
    r"\bonly\s+open\s+to\s+residents\s+of\s+(?:the\s+)?(?:us|u\.s\.|usa|united\s+states|uk|u\.k\.|canada)\b",
    r"\buk\s+only\b",
    r"\bu\.k\.\s+only\b",
    r"\bcanada\s+only\b",
]

RESTRICTED_NON_INDIA = [
    "united states", "usa", "us only", "canada only", "uk only", "germany only",
    "brazil", "latin america", "remote - amer", "remote, amer", "remote - emea",
    "remote - dach", "namer", "latam", "emea only",
]

DISALLOWED_URL_SUBSTRINGS = [
    "myworkdayjobs.com",
    "taleo.net",
]


def clean_html(raw_html: str) -> str:
    """Strips HTML tags, unescapes HTML entities, and normalizes whitespace."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(raw_html))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_eligible_for_india(
    location: str = "",
    title_or_desc: str = "",
    desc_or_url: str = "",
    url_or_title: str = "",
    **kwargs: Any,
) -> bool:
    """
    Evaluates whether a job position is open to candidates located in India.
    Supports both positional (location, title, description) and keyword signatures.
    - REJECT if URL points to legacy high-friction ATS ('myworkdayjobs.com', 'taleo.net').
    - REJECT if description or location contains US/EU/W2/C2C residency restrictions.
    - ALLOW if location or body includes: "india", "worldwide", "anywhere", "global", "apac", "remote".
    """
    all_texts = [
        str(x or "")
        for x in [location, title_or_desc, desc_or_url, url_or_title]
        + list(kwargs.values())
    ]

    # 1. Reject legacy friction ATS URLs
    for text in all_texts:
        t_low = text.lower()
        for bad_url in DISALLOWED_URL_SUBSTRINGS:
            if bad_url in t_low:
                return False

    loc_lower = (location or "").lower().strip()
    full_text = " ".join(t.lower() for t in all_texts)

    # 2. Strict exclusions
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, full_text):
            return False

    # 3. Explicitly restricted non-India territory check on location
    has_global_or_india = any(
        k in loc_lower
        for k in [
            "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad",
            "pune", "worldwide", "anywhere", "global", "apac", "asia"
        ]
    )
    if not has_global_or_india:
        for r_loc in RESTRICTED_NON_INDIA:
            if r_loc in loc_lower:
                return False

    # 4. Acceptance criteria: Must contain at least one allowed term
    return any(term in full_text for term in ALLOW_TERMS)


def normalize_job(
    id_: Any,
    title: Any,
    company: Any,
    url: Any,
    location: Any,
    description: Any,
    portal: Any,
) -> Dict[str, str]:
    """
    Normalizes a job dictionary strictly to the required schema:
    {"id": str, "title": str, "company": str, "url": str, "location": str, "description": str, "portal": str}
    """
    clean_desc = clean_html(str(description or ""))
    str_url = str(url or "").strip()
    str_company = str(company or "").strip() or "Unknown"
    str_title = str(title or "").strip() or "Untitled Role"
    str_loc = str(location or "").strip() or "Remote"
    str_portal = str(portal or "").strip() or "Unknown"

    str_id = str(id_ or "").strip()
    if not str_id:
        str_id = hashlib.sha256(f"{str_company}_{str_title}_{str_url}".encode("utf-8")).hexdigest()[:16]

    return {
        "id": str_id,
        "title": str_title,
        "company": str_company,
        "url": str_url,
        "location": str_loc,
        "description": clean_desc,
        "portal": str_portal,
    }


def _matches_keyword(job: Dict[str, str], keyword: str) -> bool:
    """Checks if job matches keyword query (case-insensitive substring or all tokens)."""
    if not keyword:
        return True
    kw = keyword.lower().strip()
    tokens = kw.split()
    target = f"{job['title']} {job['company']} {job['description']}".lower()
    return (kw in target) or all(t in target for t in tokens)


class JobSearchService:
    """Unified zero-login multi-source scraper and search aggregator."""

    PORTALS = [
        "All Sources (India Eligible)",
        "Target Companies (Greenhouse / Ashby / Lever)",
        "Jobicy (APAC / Remote)",
        "Himalayas (India)",
        "WeWorkRemotely",
        "Remotive",
        "RemoteOK",
        "Arbeitnow",
        "Dev.to",
    ]

    GREENHOUSE_COMPANIES = [
        {"name": "GitLab", "board": "gitlab"},
        {"name": "Canonical", "board": "canonical"},
        {"name": "Automattic", "board": "automattic"},
        {"name": "DuckDuckGo", "board": "duckduckgo"},
        {"name": "Wikimedia Foundation", "board": "wikimedia"},
        {"name": "Remote.com", "board": "remotecom"},
        {"name": "Postman", "board": "postman"},
        {"name": "Elastic", "board": "elastic"},
        {"name": "Cockroach Labs", "board": "cockroachlabs"},
        {"name": "GitHub", "board": "github"},
    ]

    ASHBY_COMPANIES = [
        {"name": "Supabase", "board": "supabase"},
        {"name": "Zapier", "board": "zapier"},
        {"name": "Deel", "board": "deel"},
        {"name": "OpenAI", "board": "openai"},
        {"name": "Replit", "board": "replit"},
        {"name": "Linear", "board": "linear"},
        {"name": "Anysphere", "board": "anysphere"},
    ]

    LEVER_COMPANIES = [
        {"name": "Palantir", "board": "palantir"},
        {"name": "Kinsta", "board": "kinsta"},
        {"name": "Buffer", "board": "buffer"},
        {"name": "Auth0", "board": "auth0"},
    ]

    # Backward compatibility aliases
    TARGET_GREENHOUSE_COMPANIES = GREENHOUSE_COMPANIES
    TARGET_ASHBY_COMPANIES = ASHBY_COMPANIES
    TARGET_LEVER_COMPANIES = LEVER_COMPANIES

    # ---------------- 1. GREENHOUSE PUBLIC APIS ----------------

    @classmethod
    def _fetch_greenhouse_board(cls, company_name: str, board_token: str) -> List[Dict[str, str]]:
        cache_key = f"gh_{board_token}"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    content = item.get("content", "")
                    loc = item.get("location", {}).get("name") or "Remote"
                    url_job = item.get("absolute_url") or ""
                    job_id = str(item.get("id") or "")

                    if is_eligible_for_india(loc, content, url_job, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=company_name,
                                url=url_job,
                                location=loc,
                                description=content,
                                portal=f"Greenhouse ({company_name})",
                            )
                        )
            elif resp.status_code != 404:
                logger.debug("Greenhouse board %s status %d", board_token, resp.status_code)
        except Exception as e:
            logger.debug("Greenhouse board %s error: %s", board_token, e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return jobs

    @classmethod
    def fetch_all_greenhouse(cls, keyword: str = "") -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(cls._fetch_greenhouse_board, co["name"], co["board"])
                for co in cls.GREENHOUSE_COMPANIES
            ]
            for f in as_completed(futures):
                try:
                    results.extend(f.result())
                except Exception as e:
                    logger.debug("Error in greenhouse task: %s", e)
        if keyword:
            results = [j for j in results if _matches_keyword(j, keyword)]
        return results

    # ---------------- 2. ASHBY PUBLIC APIS ----------------

    @classmethod
    def _fetch_ashby_board(cls, company_name: str, board_token: str) -> List[Dict[str, str]]:
        cache_key = f"ashby_{board_token}"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    desc = item.get("descriptionHtml") or item.get("descriptionPlain") or ""
                    loc = item.get("location") or "Remote"
                    url_job = item.get("jobUrl") or ""
                    job_id = str(item.get("id") or "")

                    if is_eligible_for_india(loc, desc, url_job, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=company_name,
                                url=url_job,
                                location=loc,
                                description=desc,
                                portal=f"Ashby ({company_name})",
                            )
                        )
            elif resp.status_code != 404:
                logger.debug("Ashby board %s status %d", board_token, resp.status_code)
        except Exception as e:
            logger.debug("Ashby board %s error: %s", board_token, e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return jobs

    @classmethod
    def fetch_all_ashby(cls, keyword: str = "") -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = [
                executor.submit(cls._fetch_ashby_board, co["name"], co["board"])
                for co in cls.ASHBY_COMPANIES
            ]
            for f in as_completed(futures):
                try:
                    results.extend(f.result())
                except Exception as e:
                    logger.debug("Error in ashby task: %s", e)
        if keyword:
            results = [j for j in results if _matches_keyword(j, keyword)]
        return results

    # ---------------- 3. LEVER PUBLIC APIS ----------------

    @classmethod
    def _fetch_lever_board(cls, company_name: str, board_token: str) -> List[Dict[str, str]]:
        cache_key = f"lever_{board_token}"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        title = item.get("text", "")
                        desc = item.get("descriptionPlain") or item.get("description") or ""
                        categories = item.get("categories") or {}
                        loc = categories.get("location") or "Remote"
                        url_job = item.get("hostedUrl") or item.get("applyUrl") or ""
                        job_id = str(item.get("id") or "")

                        if is_eligible_for_india(loc, desc, url_job, title):
                            jobs.append(
                                normalize_job(
                                    id_=job_id,
                                    title=title,
                                    company=company_name,
                                    url=url_job,
                                    location=loc,
                                    description=desc,
                                    portal=f"Lever ({company_name})",
                                )
                            )
            elif resp.status_code != 404:
                logger.debug("Lever board %s status %d", board_token, resp.status_code)
        except Exception as e:
            logger.debug("Lever board %s error: %s", board_token, e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return jobs

    @classmethod
    def fetch_all_lever(cls, keyword: str = "") -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(cls._fetch_lever_board, co["name"], co["board"])
                for co in cls.LEVER_COMPANIES
            ]
            for f in as_completed(futures):
                try:
                    results.extend(f.result())
                except Exception as e:
                    logger.debug("Error in lever task: %s", e)
        if keyword:
            results = [j for j in results if _matches_keyword(j, keyword)]
        return results

    # ---------------- 4. PUBLIC AGGREGATOR APIS ----------------

    @classmethod
    def fetch_jobicy(cls, keyword: str = "") -> List[Dict[str, str]]:
        cache_key = "agg_jobicy"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                jobs = cached[1]
                return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

        url = "https://jobicy.com/api/v2/remote-jobs?count=50&geo=apac"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("jobTitle", "")
                    desc = item.get("jobDescription", "")
                    comp = item.get("companyName") or "Unknown"
                    loc = item.get("jobGeo") or item.get("jobLocation") or "APAC (Remote)"
                    url_job = item.get("url") or ""
                    job_id = str(item.get("id") or "")

                    if is_eligible_for_india(loc, desc, url_job, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=comp,
                                url=url_job,
                                location=loc,
                                description=desc,
                                portal="Jobicy",
                            )
                        )
        except Exception as e:
            logger.warning("Jobicy fetch failed: %s", e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

    @classmethod
    def fetch_remotive(cls, keyword: str = "") -> List[Dict[str, str]]:
        cache_key = f"agg_remotive_{keyword.strip().lower()}" if keyword else "agg_remotive_all"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        if keyword:
            url = f"https://remotive.com/api/remote-jobs?search={requests.utils.quote(keyword)}&limit=50"
        else:
            url = "https://remotive.com/api/remote-jobs?limit=50"

        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    desc = item.get("description", "")
                    comp = item.get("company_name") or "Unknown"
                    loc = item.get("candidate_required_location") or "Remote"
                    url_job = item.get("url") or ""
                    job_id = str(item.get("id") or "")

                    if is_eligible_for_india(loc, desc, url_job, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=comp,
                                url=url_job,
                                location=loc,
                                description=desc,
                                portal="Remotive",
                            )
                        )
        except Exception as e:
            logger.warning("Remotive fetch failed: %s", e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return jobs

    @classmethod
    def fetch_remoteok(cls, keyword: str = "") -> List[Dict[str, str]]:
        cache_key = f"agg_remoteok_{keyword.strip().lower()}" if keyword else "agg_remoteok_all"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        if keyword:
            url = f"https://remoteok.com/api?tag={requests.utils.quote(keyword)}"
        else:
            url = "https://remoteok.com/api"

        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 1:
                    for item in data[1:]:
                        if not isinstance(item, dict):
                            continue
                        pos = item.get("position", "")
                        desc = item.get("description", "")
                        comp = item.get("company") or "Unknown"
                        loc = item.get("location") or "Remote (Worldwide)"
                        url_job = item.get("url") or ""
                        job_id = str(item.get("id") or "")

                        if is_eligible_for_india(loc, desc, url_job, pos):
                            jobs.append(
                                normalize_job(
                                    id_=job_id,
                                    title=pos,
                                    company=comp,
                                    url=url_job,
                                    location=loc,
                                    description=desc,
                                    portal="RemoteOK",
                                )
                            )
                            if len(jobs) >= 50:
                                break
        except Exception as e:
            logger.warning("RemoteOK fetch failed: %s", e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return jobs

    @classmethod
    def fetch_himalayas(cls, keyword: str = "") -> List[Dict[str, str]]:
        cache_key = "agg_himalayas"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                jobs = cached[1]
                return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

        url = "https://himalayas.app/jobs/api?country=India"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    desc = item.get("description", "")
                    comp = item.get("companyName") or "Unknown"
                    loc = item.get("location") or "India (Remote)"
                    url_job = item.get("applicationLink") or item.get("url") or ""
                    job_id = str(item.get("id") or item.get("slug") or "")

                    if is_eligible_for_india(loc, desc, url_job, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=comp,
                                url=url_job,
                                location=loc,
                                description=desc,
                                portal="Himalayas",
                            )
                        )
        except Exception as e:
            logger.warning("Himalayas fetch failed: %s", e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

    @classmethod
    def fetch_arbeitnow(cls, keyword: str = "") -> List[Dict[str, str]]:
        cache_key = "agg_arbeitnow"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                jobs = cached[1]
                return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

        url = "https://www.arbeitnow.com/api/job-board-api"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    title = item.get("title", "")
                    desc = item.get("description", "")
                    comp = item.get("company_name") or "Unknown"
                    is_remote = bool(item.get("remote"))
                    loc = item.get("location") or ("Remote" if is_remote else "Worldwide")
                    url_job = item.get("url") or ""
                    job_id = str(item.get("slug") or "")

                    if is_eligible_for_india(loc, desc, url_job, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=comp,
                                url=url_job,
                                location=loc,
                                description=desc,
                                portal="Arbeitnow",
                            )
                        )
        except Exception as e:
            logger.warning("Arbeitnow fetch failed: %s", e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

    @classmethod
    def fetch_all_aggregators(cls, keyword: str = "") -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(cls.fetch_jobicy, keyword),
                executor.submit(cls.fetch_remotive, keyword),
                executor.submit(cls.fetch_remoteok, keyword),
                executor.submit(cls.fetch_himalayas, keyword),
                executor.submit(cls.fetch_arbeitnow, keyword),
            ]
            for f in as_completed(futures):
                try:
                    results.extend(f.result())
                except Exception as e:
                    logger.debug("Aggregator error: %s", e)
        return results

    # ---------------- 5. RSS FEEDS ----------------

    @classmethod
    def fetch_weworkremotely(cls, keyword: str = "") -> List[Dict[str, str]]:
        cache_key = "rss_wwr"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                jobs = cached[1]
                return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

        url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                for entry in feed.entries:
                    raw_title = getattr(entry, "title", "")
                    company = "Unknown"
                    title = raw_title
                    if ":" in raw_title:
                        parts = raw_title.split(":", 1)
                        company = parts[0].strip()
                        title = parts[1].strip()

                    desc = getattr(entry, "summary", getattr(entry, "description", ""))
                    link = getattr(entry, "link", "")
                    job_id = str(getattr(entry, "id", link))
                    loc = "Worldwide (Remote)"

                    if is_eligible_for_india(loc, desc, link, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=company,
                                url=link,
                                location=loc,
                                description=desc,
                                portal="WeWorkRemotely",
                            )
                        )
        except Exception as e:
            logger.warning("WeWorkRemotely RSS fetch failed: %s", e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

    # Alias for backward compatibility
    fetch_wwr = fetch_weworkremotely

    @classmethod
    def fetch_devto(cls, keyword: str = "") -> List[Dict[str, str]]:
        cache_key = "rss_devto"
        now = time.time()
        with _CACHE_LOCK:
            cached = _IN_MEMORY_CACHE.get(cache_key)
            if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
                jobs = cached[1]
                return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

        url = "https://dev.to/feed/tag/jobs"
        jobs: List[Dict[str, str]] = []
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                for entry in feed.entries:
                    title = getattr(entry, "title", "")
                    desc = getattr(entry, "summary", getattr(entry, "description", ""))
                    comp = getattr(entry, "author", "Dev.to")
                    link = getattr(entry, "link", "")
                    job_id = str(getattr(entry, "id", link))
                    loc = "Remote"

                    if is_eligible_for_india(loc, desc, link, title):
                        jobs.append(
                            normalize_job(
                                id_=job_id,
                                title=title,
                                company=comp,
                                url=link,
                                location=loc,
                                description=desc,
                                portal="Dev.to",
                            )
                        )
        except Exception as e:
            logger.warning("Dev.to RSS fetch failed: %s", e)

        with _CACHE_LOCK:
            _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return [j for j in jobs if _matches_keyword(j, keyword)] if keyword else jobs

    @classmethod
    def fetch_all_rss(cls, keyword: str = "") -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(cls.fetch_weworkremotely, keyword),
                executor.submit(cls.fetch_devto, keyword),
            ]
            for f in as_completed(futures):
                try:
                    results.extend(f.result())
                except Exception as e:
                    logger.debug("RSS error: %s", e)
        return results

    # ---------------- 6. COMBINED TARGET COMPANIES ----------------

    @classmethod
    def fetch_all_target_companies(cls, keyword: str = "") -> List[Dict[str, str]]:
        """Fetches from Greenhouse, Ashby, and Lever target companies in parallel."""
        results: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            f_gh = executor.submit(cls.fetch_all_greenhouse, keyword)
            f_ashby = executor.submit(cls.fetch_all_ashby, keyword)
            f_lever = executor.submit(cls.fetch_all_lever, keyword)

            for f in as_completed([f_gh, f_ashby, f_lever]):
                try:
                    results.extend(f.result())
                except Exception as e:
                    logger.debug("Target company gathering error: %s", e)
        return results

    # ---------------- 7. UNIFIED SEARCH DISPATCHER ----------------

    @classmethod
    def search(
        cls,
        keyword: str = "",
        portal: str = "All Sources (India Eligible)",
        max_total: int = 50,
    ) -> List[Dict[str, str]]:
        """
        Unified search dispatcher across selected portal category or all sources.
        Guarantees India remote eligibility filtering and exact dictionary normalization.
        """
        kw = keyword.strip()
        p_low = portal.lower().strip()

        # Specific Portal Selections
        if "greenhouse" in p_low:
            jobs = cls.fetch_all_greenhouse(kw)
        elif "ashby" in p_low:
            jobs = cls.fetch_all_ashby(kw)
        elif "lever" in p_low:
            jobs = cls.fetch_all_lever(kw)
        elif "target" in p_low:
            jobs = cls.fetch_all_target_companies(kw)
        elif "jobicy" in p_low:
            jobs = cls.fetch_jobicy(kw)
        elif "himalayas" in p_low:
            jobs = cls.fetch_himalayas(kw)
        elif "weworkremotely" in p_low or "wwr" in p_low:
            jobs = cls.fetch_weworkremotely(kw)
        elif "remotive" in p_low:
            jobs = cls.fetch_remotive(kw)
        elif "remoteok" in p_low:
            jobs = cls.fetch_remoteok(kw)
        elif "arbeitnow" in p_low:
            jobs = cls.fetch_arbeitnow(kw)
        elif "dev.to" in p_low or "devto" in p_low:
            jobs = cls.fetch_devto(kw)
        else:
            # "All Sources (India Eligible)" — Fetch target companies, aggregators & RSS concurrently
            combined: List[Dict[str, str]] = []
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(cls.fetch_all_target_companies, kw),
                    executor.submit(cls.fetch_jobicy, kw),
                    executor.submit(cls.fetch_remotive, kw),
                    executor.submit(cls.fetch_remoteok, kw),
                    executor.submit(cls.fetch_himalayas, kw),
                    executor.submit(cls.fetch_arbeitnow, kw),
                    executor.submit(cls.fetch_weworkremotely, kw),
                    executor.submit(cls.fetch_devto, kw),
                ]
                for f in as_completed(futures):
                    try:
                        combined.extend(f.result())
                    except Exception as e:
                        logger.error("Error gathering feed results: %s", e)
            jobs = combined

        # Deduplicate strictly by URL or fallback key
        seen_keys = set()
        deduped: List[Dict[str, str]] = []
        for j in jobs:
            dedup_key = (j.get("url") or f"{j.get('company')}_{j.get('title')}").strip().lower()
            if dedup_key and dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                deduped.append(j)

        return deduped[:max_total]


class ZeroLoginJobFetcher:
    """Convenience multi-keyword job fetcher across zero-login sources."""

    @classmethod
    def get_all_jobs(
        cls,
        keywords: Optional[List[str]] = None,
        max_per_kw: int = 25,
    ) -> List[Dict[str, str]]:
        """Fetches and deduplicates jobs across specified keywords."""
        target_kws = keywords or ["Python AI", "AI Agent", "LLM", "Automation"]
        combined: List[Dict[str, str]] = []
        seen_urls = set()

        for kw in target_kws:
            jobs = JobSearchService.search(keyword=kw, portal="All Sources (India Eligible)", max_total=max_per_kw)
            for j in jobs:
                u = (j.get("url") or f"{j.get('company')}_{j.get('title')}").strip().lower()
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    combined.append(j)

        return combined
