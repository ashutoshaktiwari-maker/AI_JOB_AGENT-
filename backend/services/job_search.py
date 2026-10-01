"""
Multi-Portal Job Search Service.
Queries verified portals (RemoteOK, Remotive, Arbeitnow) with concurrent execution,
standardized schemas, and explicit portal source tracking.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


def clean_html(raw_html: str) -> str:
    """Removes HTML tags and normalizes whitespace."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


class JobSearchService:
    PORTALS = ["All Portals", "RemoteOK", "Remotive", "Arbeitnow"]

    @staticmethod
    def search_remoteok(keyword: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Queries RemoteOK API and returns jobs tagged with portal='RemoteOK'."""
        url = "https://remoteok.com/api"
        headers = {"User-Agent": "Mozilla/5.0"}
        jobs: List[Dict[str, Any]] = []

        try:
            resp = requests.get(url, headers=headers, timeout=12)
            resp.raise_for_status()
            data = resp.json()

            for item in data[1:]:
                position = item.get("position", "")
                description = item.get("description", "")
                tags = item.get("tags", [])
                text = f"{position} {description} {' '.join(tags)}".lower()

                if keyword.lower() in text:
                    jobs.append({
                        "portal": "RemoteOK",
                        "company": item.get("company", "Unknown"),
                        "title": position,
                        "location": item.get("location") or "Remote (Worldwide)",
                        "url": item.get("url") or "",
                        "tags": tags,
                        "description": clean_html(description),
                        "date_posted": item.get("date", ""),
                    })
                    if len(jobs) >= limit:
                        break
        except Exception as e:
            logger.warning("RemoteOK fetch failed: %s", e)

        return jobs

    @staticmethod
    def search_remotive(keyword: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Queries Remotive API and returns jobs tagged with portal='Remotive'."""
        url = f"https://remotive.com/api/remote-jobs?search={requests.utils.quote(keyword)}&limit={limit}"
        jobs: List[Dict[str, Any]] = []

        try:
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("jobs", []):
                jobs.append({
                    "portal": "Remotive",
                    "company": item.get("company_name", "Unknown"),
                    "title": item.get("title", ""),
                    "location": item.get("candidate_required_location") or "Remote",
                    "url": item.get("url") or "",
                    "tags": item.get("tags", []),
                    "description": clean_html(item.get("description", "")),
                    "date_posted": item.get("publication_date", ""),
                })
                if len(jobs) >= limit:
                    break
        except Exception as e:
            logger.warning("Remotive fetch failed: %s", e)

        return jobs

    @staticmethod
    def search_arbeitnow(keyword: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Queries Arbeitnow Job Board API and returns jobs tagged with portal='Arbeitnow'."""
        url = "https://www.arbeitnow.com/api/job-board-api"
        jobs: List[Dict[str, Any]] = []

        try:
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", []):
                title = item.get("title", "")
                description = item.get("description", "")
                tags = item.get("tags", [])
                text = f"{title} {description} {' '.join(tags)}".lower()

                if keyword.lower() in text:
                    loc = item.get("location", "")
                    if item.get("remote"):
                        loc = f"{loc} (Remote)" if loc else "Remote"

                    jobs.append({
                        "portal": "Arbeitnow",
                        "company": item.get("company_name", "Unknown"),
                        "title": title,
                        "location": loc or "Remote",
                        "url": item.get("url") or "",
                        "tags": tags,
                        "description": clean_html(description),
                        "date_posted": item.get("created_at", ""),
                    })
                    if len(jobs) >= limit:
                        break
        except Exception as e:
            logger.warning("Arbeitnow fetch failed: %s", e)

        return jobs

    @classmethod
    def search(cls, keyword: str, portal: str = "All Portals", max_total: int = 30) -> List[Dict[str, Any]]:
        """
        Unified search across selected portal or all portals in parallel.
        Every returned job includes the 'portal' attribute.
        """
        keyword = keyword.strip()
        if not keyword:
            return []

        if portal == "RemoteOK":
            return cls.search_remoteok(keyword, limit=max_total)
        elif portal == "Remotive":
            return cls.search_remotive(keyword, limit=max_total)
        elif portal == "Arbeitnow":
            return cls.search_arbeitnow(keyword, limit=max_total)

        # "All Portals" - Search concurrently
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_portal = {
                executor.submit(cls.search_remoteok, keyword, 15): "RemoteOK",
                executor.submit(cls.search_remotive, keyword, 15): "Remotive",
                executor.submit(cls.search_arbeitnow, keyword, 15): "Arbeitnow",
            }

            for future in as_completed(future_to_portal):
                portal_name = future_to_portal[future]
                try:
                    portal_jobs = future.result()
                    results.extend(portal_jobs)
                except Exception as exc:
                    logger.error("Portal %s search failed: %s", portal_name, exc)

        # Sort so portals are pleasantly distributed, or return up to max_total
        return results[:max_total]
