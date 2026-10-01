"""
Daily Job and Keyword Tracking Service.
Tracks search keywords, daily job discovery volume, and portal activity for candidate email:
ashutosh.aktiwari@gmail.com
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.job_search import JobSearchService

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRACKER_FILE = DATA_DIR / "daily_tracker.json"

DEFAULT_EMAIL = "ashutosh.aktiwari@gmail.com"
DEFAULT_KEYWORDS = [
    "Python AI",
    "AI Automation",
    "Prompt Engineer",
    "AI Agents",
    "Workflow Automation",
    "n8n",
]


class DailyJobTracker:
    """Manages daily job keyword tracking, scan history, and metrics per user email."""

    @classmethod
    def _load_data(cls) -> Dict[str, Any]:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not TRACKER_FILE.exists():
            initial = {
                "user_email": DEFAULT_EMAIL,
                "tracked_keywords": DEFAULT_KEYWORDS,
                "history": [],
                "last_scan": None,
            }
            cls._save_data(initial)
            return initial

        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not data.get("user_email"):
                    data["user_email"] = DEFAULT_EMAIL
                if not data.get("tracked_keywords"):
                    data["tracked_keywords"] = DEFAULT_KEYWORDS
                return data
        except Exception as e:
            logger.error("Failed loading daily_tracker.json: %s", e)
            return {
                "user_email": DEFAULT_EMAIL,
                "tracked_keywords": DEFAULT_KEYWORDS,
                "history": [],
                "last_scan": None,
            }

    @classmethod
    def _save_data(cls, data: Dict[str, Any]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(TRACKER_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed saving daily_tracker.json: %s", e)

    @classmethod
    def get_tracked_email(cls) -> str:
        data = cls._load_data()
        return data.get("user_email", DEFAULT_EMAIL)

    @classmethod
    def set_tracked_email(cls, email: str) -> str:
        data = cls._load_data()
        data["user_email"] = email.strip()
        cls._save_data(data)
        return data["user_email"]

    @classmethod
    def get_tracked_keywords(cls) -> List[str]:
        data = cls._load_data()
        return data.get("tracked_keywords", DEFAULT_KEYWORDS)

    @classmethod
    def add_tracked_keyword(cls, keyword: str) -> List[str]:
        kw = keyword.strip()
        if not kw:
            return cls.get_tracked_keywords()
        data = cls._load_data()
        keywords = data.get("tracked_keywords", DEFAULT_KEYWORDS)
        if kw not in keywords:
            keywords.append(kw)
            data["tracked_keywords"] = keywords
            cls._save_data(data)
        return keywords

    @classmethod
    def remove_tracked_keyword(cls, keyword: str) -> List[str]:
        data = cls._load_data()
        keywords = data.get("tracked_keywords", DEFAULT_KEYWORDS)
        if keyword in keywords:
            keywords.remove(keyword)
            data["tracked_keywords"] = keywords
            cls._save_data(data)
        return keywords

    @classmethod
    def log_search(
        cls,
        keyword: str,
        portal: str,
        jobs_count: int,
        email: Optional[str] = None
    ) -> Dict[str, Any]:
        """Logs a search query event into the daily tracking history."""
        data = cls._load_data()
        user_email = email or data.get("user_email", DEFAULT_EMAIL)
        today_str = date.today().isoformat()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            "date": today_str,
            "timestamp": now_str,
            "email": user_email,
            "keyword": keyword,
            "portal": portal,
            "jobs_count": jobs_count,
        }

        history = data.get("history", [])
        # Prepend latest
        history.insert(0, entry)
        # Keep last 100 entries
        data["history"] = history[:100]
        cls._save_data(data)
        return entry

    @classmethod
    def get_history(cls, limit: int = 20) -> List[Dict[str, Any]]:
        data = cls._load_data()
        return data.get("history", [])[:limit]

    @classmethod
    def run_daily_scan(cls, email: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a comprehensive scan across all tracked keywords on all portals.
        Aggregates new job opportunities and saves the scan record.
        """
        data = cls._load_data()
        target_email = email or data.get("user_email", DEFAULT_EMAIL)
        keywords = data.get("tracked_keywords", DEFAULT_KEYWORDS)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_str = date.today().isoformat()

        all_jobs: List[Dict[str, Any]] = []
        seen_urls = set()
        keyword_counts = {}

        for kw in keywords:
            found = JobSearchService.search(keyword=kw, portal="All Portals", max_total=10)
            count = 0
            for j in found:
                url = j.get("url") or f"{j.get('company')}_{j.get('title')}"
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_jobs.append(j)
                    count += 1
            keyword_counts[kw] = count

            # Log search event for each keyword
            cls.log_search(keyword=kw, portal="All Portals", jobs_count=count, email=target_email)

        scan_result = {
            "date": today_str,
            "timestamp": now_str,
            "email": target_email,
            "total_jobs_found": len(all_jobs),
            "keyword_breakdown": keyword_counts,
            "jobs": all_jobs,
        }

        data["last_scan"] = {
            "date": today_str,
            "timestamp": now_str,
            "email": target_email,
            "total_jobs_found": len(all_jobs),
        }
        cls._save_data(data)
        return scan_result
