"""
Multi-Source Job Search & Target Company Pipeline.

Ingests job postings from:
1. Target Companies & Public ATS Endpoints:
   - Greenhouse: GitLab, Automattic, Canonical, DuckDuckGo, Wikimedia, Postman, Deel, Remote.com
   - Ashby: Supabase, Zapier, Deel
2. Aggregators:
   - Remotive (https://remotive.com/api/remote-jobs)
   - RemoteOK (https://remoteok.com/api)
   - Himalayas (https://himalayas.app/jobs/api?country=India)
   - We Work Remotely RSS (https://weworkremotely.com/categories/remote-programming-jobs.rss)

Applies strict filtering for India-based / worldwide remote candidates:
- Includes: India, Worldwide, Anywhere, Global, APAC, Asia, or open Remote.
- Excludes: US Citizen, W2 Only, US/EU Only, C2C, or Must reside in [US/UK/Canada].
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

# Cache store: {cache_key: (timestamp, [jobs])}
_IN_MEMORY_CACHE: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
CACHE_TTL_SECONDS = 600  # 10 minutes cache to keep search instantaneous

# ----------------- FILTERING RULES -----------------

INCLUDE_LOCATIONS = [
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune",
    "gurgaon", "gurugram", "noida", "chennai", "kolkata", "ahmedabad",
    "worldwide", "anywhere", "global", "apac", "asia", "remote",
    "remote - global", "remote (worldwide)", "remote, worldwide", "remote - worldwide",
    "all locations", "everywhere"
]

EXCLUDE_PATTERNS = [
    r"\bus citizen\b",
    r"\bw2 only\b",
    r"\bus/eu only\b",
    r"\bus only\b",
    r"\bu\.s\. only\b",
    r"\bc2c\b",
    r"\bcorp to corp\b",
    r"\bmust reside in (?:the )?(?:us|usa|united states|uk|united kingdom|canada|eu|europe)\b",
    r"\bonly open to residents of (?:the )?(?:us|usa|united states|uk|canada)\b",
    r"\bus citizenship required\b",
    r"\b(amer|latam|emea|da-ch) only\b",
]

RESTRICTED_NON_INDIA = [
    "united states", "usa", "us only", "canada only", "uk only", "germany only",
    "brazil", "latin america", "remote - amer", "remote, amer", "remote - emea",
    "remote - dach", "namer", "latam", "emea only"
]


def clean_html(raw_html: str) -> str:
    """Strips HTML tags and normalizes whitespace."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def is_eligible_for_india(location: str, title: str = "", description: str = "") -> bool:
    """
    Evaluates whether a job position is open to candidates located in India.
    Includes: India, Worldwide, Anywhere, Global, APAC, or open Remote.
    Excludes: US Citizen, W2 Only, US/EU Only, C2C, or Must reside in [US/UK/Canada].
    """
    loc = (location or "").lower().strip()
    full_text = f"{loc} {title} {description}".lower()

    # 1. Strict Exclusions
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, full_text):
            return False

    # 2. Check if explicitly restricted to a foreign country or non-India territory
    has_global_or_india = any(
        k in loc for k in ["india", "bangalore", "mumbai", "delhi", "hyderabad", "pune", "worldwide", "anywhere", "global", "apac", "asia"]
    )
    if not has_global_or_india:
        for r_loc in RESTRICTED_NON_INDIA:
            if r_loc in loc:
                return False

    # 3. Acceptance Criteria
    if not loc or loc == "remote":
        return True

    return any(k in loc for k in INCLUDE_LOCATIONS)


class JobSearchService:
    """High-performance aggregator for target companies and remote job boards."""

    PORTALS = [
        "All Sources (India Eligible)",
        "Target Companies (GitLab, Supabase, Canonical, Zapier...)",
        "Himalayas (India)",
        "WeWorkRemotely",
        "Remotive",
        "RemoteOK",
    ]

    # Target Companies on Greenhouse
    TARGET_GREENHOUSE_COMPANIES = [
        {"name": "GitLab", "board": "gitlab"},
        {"name": "Automattic", "board": "automattic"},
        {"name": "Canonical", "board": "canonical"},
        {"name": "DuckDuckGo", "board": "duckduckgo"},
        {"name": "Wikimedia Foundation", "board": "wikimedia"},
        {"name": "Postman", "board": "postman"},
        {"name": "Deel", "board": "deel"},
        {"name": "Remote.com", "board": "remotecom"},
    ]

    # Target Companies on Ashby
    TARGET_ASHBY_COMPANIES = [
        {"name": "Supabase", "board": "supabase"},
        {"name": "Zapier", "board": "zapier"},
        {"name": "Deel (Ashby)", "board": "deel"},
    ]

    @classmethod
    def _fetch_greenhouse_board(cls, company_name: str, board_token: str) -> List[Dict[str, Any]]:
        """Fetches all jobs for a target company via public Greenhouse API."""
        cache_key = f"gh_{board_token}"
        cached = _IN_MEMORY_CACHE.get(cache_key)
        now = time.time()
        if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
            return cached[1]

        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=7)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    content = clean_html(item.get("content", ""))
                    loc_name = item.get("location", {}).get("name") or "Remote"
                    url_job = item.get("absolute_url") or ""

                    if is_eligible_for_india(loc_name, title, content):
                        jobs.append({
                            "portal": f"Greenhouse ({company_name})",
                            "company": company_name,
                            "title": title,
                            "location": loc_name,
                            "url": url_job,
                            "tags": [company_name, "Greenhouse", "India Eligible"],
                            "description": content,
                            "date_posted": item.get("updated_at", ""),
                            "eligible_for_india": True,
                            "source_type": "Target Company",
                        })
            elif resp.status_code != 404:
                logger.debug("Greenhouse board %s status %d", board_token, resp.status_code)
        except Exception as e:
            logger.debug("Greenhouse board %s error: %s", board_token, e)

        _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return jobs

    @classmethod
    def _fetch_ashby_board(cls, company_name: str, board_token: str) -> List[Dict[str, Any]]:
        """Fetches all jobs for a target company via public Ashby API."""
        cache_key = f"ashby_{board_token}"
        cached = _IN_MEMORY_CACHE.get(cache_key)
        now = time.time()
        if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
            return cached[1]

        url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=7)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    desc = clean_html(item.get("descriptionHtml", ""))
                    loc_name = item.get("location") or "Remote"
                    url_job = item.get("jobUrl") or ""

                    if is_eligible_for_india(loc_name, title, desc):
                        jobs.append({
                            "portal": f"Ashby ({company_name})",
                            "company": company_name,
                            "title": title,
                            "location": loc_name,
                            "url": url_job,
                            "tags": [company_name, "Ashby", "India Eligible"],
                            "description": desc,
                            "date_posted": item.get("publishedAt", ""),
                            "eligible_for_india": True,
                            "source_type": "Target Company",
                        })
        except Exception as e:
            logger.debug("Ashby board %s error: %s", board_token, e)

        _IN_MEMORY_CACHE[cache_key] = (now, jobs)
        return jobs

    @classmethod
    def fetch_himalayas(cls, keyword: str = "") -> List[Dict[str, Any]]:
        """Fetches India-eligible remote positions from Himalayas API."""
        cache_key = "himalayas_india"
        cached = _IN_MEMORY_CACHE.get(cache_key)
        now = time.time()
        raw_jobs = []

        if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
            raw_jobs = cached[1]
        else:
            url = "https://himalayas.app/jobs/api?country=India"
            try:
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("jobs", []):
                        title = item.get("title", "")
                        desc = clean_html(item.get("description", ""))
                        loc = item.get("location") or "India (Remote)"
                        cats = [c.get("name") for c in item.get("categories", []) if isinstance(c, dict)] or item.get("categories") or []

                        if is_eligible_for_india(loc, title, desc):
                            raw_jobs.append({
                                "portal": "Himalayas",
                                "company": item.get("companyName") or "Unknown",
                                "title": title,
                                "location": loc,
                                "url": item.get("applicationLink") or item.get("url") or "",
                                "tags": list(cats) + ["India Eligible"],
                                "description": desc,
                                "date_posted": item.get("pubDate", ""),
                                "eligible_for_india": True,
                                "source_type": "Aggregator",
                            })
                    _IN_MEMORY_CACHE[cache_key] = (now, raw_jobs)
            except Exception as e:
                logger.warning("Himalayas fetch failed: %s", e)

        if not keyword:
            return raw_jobs
        return [
            j for j in raw_jobs
            if keyword.lower() in f"{j['title']} {j['company']} {j['description']} {' '.join(j.get('tags', []))}".lower()
        ]

    @classmethod
    def fetch_wwr(cls, keyword: str = "") -> List[Dict[str, Any]]:
        """Fetches remote programming roles from We Work Remotely RSS feed."""
        cache_key = "wwr_rss"
        cached = _IN_MEMORY_CACHE.get(cache_key)
        now = time.time()
        raw_jobs = []

        if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
            raw_jobs = cached[1]
        else:
            url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
            try:
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    channel = root.find("channel")
                    items = channel.findall("item") if channel is not None else []
                    for it in items:
                        raw_title = it.findtext("title") or ""
                        company = "Unknown"
                        title = raw_title
                        if ":" in raw_title:
                            parts = raw_title.split(":", 1)
                            company = parts[0].strip()
                            title = parts[1].strip()

                        desc = clean_html(it.findtext("description") or "")
                        link = it.findtext("link") or ""
                        loc = "Worldwide (Remote)"
                        pub = it.findtext("pubDate") or ""

                        if is_eligible_for_india(loc, title, desc):
                            raw_jobs.append({
                                "portal": "WeWorkRemotely",
                                "company": company,
                                "title": title,
                                "location": loc,
                                "url": link,
                                "tags": ["WeWorkRemotely", "Remote", "India Eligible"],
                                "description": desc,
                                "date_posted": pub,
                                "eligible_for_india": True,
                                "source_type": "Aggregator",
                            })
                    _IN_MEMORY_CACHE[cache_key] = (now, raw_jobs)
            except Exception as e:
                logger.warning("WeWorkRemotely fetch failed: %s", e)

        if not keyword:
            return raw_jobs
        return [
            j for j in raw_jobs
            if keyword.lower() in f"{j['title']} {j['company']} {j['description']}".lower()
        ]

    @classmethod
    def fetch_remotive(cls, keyword: str = "") -> List[Dict[str, Any]]:
        """Queries Remotive API for remote roles."""
        url = f"https://remotive.com/api/remote-jobs?search={requests.utils.quote(keyword)}&limit=25" if keyword else "https://remotive.com/api/remote-jobs?limit=25"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = requests.get(url, timeout=9)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    loc = item.get("candidate_required_location") or "Remote"
                    desc = clean_html(item.get("description", ""))
                    if is_eligible_for_india(loc, title, desc):
                        jobs.append({
                            "portal": "Remotive",
                            "company": item.get("company_name", "Unknown"),
                            "title": title,
                            "location": loc,
                            "url": item.get("url") or "",
                            "tags": item.get("tags", []) + ["India Eligible"],
                            "description": desc,
                            "date_posted": item.get("publication_date", ""),
                            "eligible_for_india": True,
                            "source_type": "Aggregator",
                        })
        except Exception as e:
            logger.warning("Remotive fetch failed: %s", e)
        return jobs

    @classmethod
    def fetch_remoteok(cls, keyword: str = "") -> List[Dict[str, Any]]:
        """Queries RemoteOK API for remote roles."""
        url = "https://remoteok.com/api"
        headers = {"User-Agent": "Mozilla/5.0"}
        jobs: List[Dict[str, Any]] = []
        try:
            resp = requests.get(url, headers=headers, timeout=9)
            if resp.status_code == 200:
                data = resp.json()
                for item in data[1:]:
                    pos = item.get("position", "")
                    desc = clean_html(item.get("description", ""))
                    tags = item.get("tags", [])
                    loc = item.get("location") or "Remote (Worldwide)"

                    if keyword and keyword.lower() not in f"{pos} {desc} {' '.join(tags)}".lower():
                        continue

                    if is_eligible_for_india(loc, pos, desc):
                        jobs.append({
                            "portal": "RemoteOK",
                            "company": item.get("company", "Unknown"),
                            "title": pos,
                            "location": loc,
                            "url": item.get("url") or "",
                            "tags": tags + ["India Eligible"],
                            "description": desc,
                            "date_posted": item.get("date", ""),
                            "eligible_for_india": True,
                            "source_type": "Aggregator",
                        })
                        if len(jobs) >= 25:
                            break
        except Exception as e:
            logger.warning("RemoteOK fetch failed: %s", e)
        return jobs

    @classmethod
    def fetch_all_target_companies(cls, keyword: str = "") -> List[Dict[str, Any]]:
        """Fetches from all target Greenhouse & Ashby company boards in parallel."""
        all_company_jobs: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_co = {}
            for gh in cls.TARGET_GREENHOUSE_COMPANIES:
                future_to_co[executor.submit(cls._fetch_greenhouse_board, gh["name"], gh["board"])] = gh["name"]
            for ash in cls.TARGET_ASHBY_COMPANIES:
                future_to_co[executor.submit(cls._fetch_ashby_board, ash["name"], ash["board"])] = ash["name"]

            for future in as_completed(future_to_co):
                co_name = future_to_co[future]
                try:
                    c_jobs = future.result()
                    if keyword:
                        c_jobs = [
                            j for j in c_jobs
                            if keyword.lower() in f"{j['title']} {j['company']} {j['description']}".lower()
                        ]
                    all_company_jobs.extend(c_jobs)
                except Exception as exc:
                    logger.debug("Company %s fetch error: %s", co_name, exc)

        return all_company_jobs

    @classmethod
    def search(cls, keyword: str, portal: str = "All Sources (India Eligible)", max_total: int = 50) -> List[Dict[str, Any]]:
        """
        Unified search dispatcher across selected portal category or all sources.
        Guarantees India eligibility filtering across all results.
        """
        keyword = keyword.strip()

        # Specific Portal Selections
        if portal == "Himalayas (India)":
            return cls.fetch_himalayas(keyword)[:max_total]
        elif portal == "WeWorkRemotely":
            return cls.fetch_wwr(keyword)[:max_total]
        elif portal == "Remotive":
            return cls.fetch_remotive(keyword)[:max_total]
        elif portal == "RemoteOK":
            return cls.fetch_remoteok(keyword)[:max_total]
        elif portal == "Target Companies (GitLab, Supabase, Canonical, Zapier...)":
            return cls.fetch_all_target_companies(keyword)[:max_total]

        # "All Sources (India Eligible)" — Fetch target companies + aggregators in parallel
        combined: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            f_targets = executor.submit(cls.fetch_all_target_companies, keyword)
            f_himalayas = executor.submit(cls.fetch_himalayas, keyword)
            f_wwr = executor.submit(cls.fetch_wwr, keyword)
            f_remotive = executor.submit(cls.fetch_remotive, keyword)
            f_remoteok = executor.submit(cls.fetch_remoteok, keyword)

            for f in as_completed([f_targets, f_himalayas, f_wwr, f_remotive, f_remoteok]):
                try:
                    res = f.result()
                    combined.extend(res)
                except Exception as e:
                    logger.error("Error gathering feed results: %s", e)

        # Deduplicate by URL
        seen_urls = set()
        deduped = []
        for j in combined:
            u = j.get("url") or f"{j.get('company')}_{j.get('title')}"
            if u not in seen_urls:
                seen_urls.add(u)
                deduped.append(j)

        return deduped[:max_total]
