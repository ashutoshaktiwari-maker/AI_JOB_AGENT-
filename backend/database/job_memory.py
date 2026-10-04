"""
Local Persistent Storage Layer for Job Deduplication & Tracking.

Database location: backend/data/jobs_memory.db
Table: saved_jobs
"""

import hashlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Allowed status transitions
VALID_STATUSES = {
    "pending_review",
    "rejected_by_user",
    "applied",
    "needs_manual_review",
}


def _resolve_db_path() -> Path:
    """Resolves database path flexibly whether called from root or backend/."""
    candidates = [
        Path("backend/data/jobs_memory.db"),
        Path("data/jobs_memory.db"),
        Path(__file__).resolve().parent.parent / "data" / "jobs_memory.db",
    ]
    for c in candidates:
        if c.parent.exists():
            return c
    # Fallback: create backend/data directory
    target = Path(__file__).resolve().parent.parent / "data" / "jobs_memory.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


DB_PATH = _resolve_db_path()


def _get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Returns a SQLite connection with Row factory enabled."""
    target_path = db_path or _resolve_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initializes the saved_jobs table schema."""
    with _get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_jobs (
                job_hash TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                location TEXT,
                portal TEXT,
                url TEXT UNIQUE,
                description TEXT,
                match_score INTEGER,
                status TEXT DEFAULT 'pending_review',
                tailored_resume_path TEXT,
                cover_letter_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                applied_at TIMESTAMP
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_jobs_url ON saved_jobs(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_jobs_status ON saved_jobs(status)")
        conn.commit()


# Automatically initialize schema on module import
init_db()


def generate_job_hash(company: str, title: str, url: str) -> str:
    """
    Computes a deterministic SHA256 hash from normalized company, title, and url.
    """
    norm_comp = (company or "").strip().lower()
    norm_title = (title or "").strip().lower()
    norm_url = (url or "").strip().lower()
    payload = f"{norm_comp}|{norm_title}|{norm_url}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_job_saved(url: str) -> bool:
    """
    Checks if a job URL has already been recorded in the database.
    """
    if not url:
        return False
    norm_url = url.strip()
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM saved_jobs WHERE url = ? OR LOWER(url) = LOWER(?) LIMIT 1",
            (norm_url, norm_url),
        )
        return cursor.fetchone() is not None


def save_discovered_job(job_dict: Dict[str, Any], match_score: int = 0) -> str:
    """
    Saves a discovered job record into saved_jobs.
    Returns the job_hash string.
    """
    company = job_dict.get("company") or "Unknown"
    title = job_dict.get("title") or "Unknown"
    url = (job_dict.get("url") or "").strip()
    location = job_dict.get("location") or "Remote"
    portal = job_dict.get("portal") or "Unknown"
    description = job_dict.get("description") or ""

    job_hash = generate_job_hash(company, title, url)

    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO saved_jobs (
                job_hash, title, company, location, portal, url,
                description, match_score, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review')
            ON CONFLICT(job_hash) DO UPDATE SET
                match_score = excluded.match_score
            """,
            (
                job_hash,
                title,
                company,
                location,
                portal,
                url,
                description,
                int(match_score or 0),
            ),
        )
        conn.commit()

    return job_hash


def update_job_assets(job_hash: str, resume_path: str, cover_letter_path: str) -> bool:
    """
    Updates the paths to the tailored resume and cover letter for a given job.
    """
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE saved_jobs
            SET tailored_resume_path = ?, cover_letter_path = ?
            WHERE job_hash = ?
            """,
            (resume_path, cover_letter_path, job_hash),
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_job_status(job_hash: str, status: str) -> bool:
    """
    Updates status for a job ('pending_review', 'rejected_by_user', 'applied', 'needs_manual_review').
    Automatically stamps applied_at timestamp when status transitions to 'applied'.
    """
    status_clean = (status or "").strip().lower()
    if status_clean not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {sorted(list(VALID_STATUSES))}"
        )

    now_iso = datetime.now().isoformat()
    with _get_connection() as conn:
        cursor = conn.cursor()
        if status_clean == "applied":
            cursor.execute(
                """
                UPDATE saved_jobs
                SET status = ?, applied_at = ?
                WHERE job_hash = ?
                """,
                (status_clean, now_iso, job_hash),
            )
        else:
            cursor.execute(
                """
                UPDATE saved_jobs
                SET status = ?
                WHERE job_hash = ?
                """,
                (status_clean, job_hash),
            )
        conn.commit()
        return cursor.rowcount > 0


def get_pending_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves up to `limit` jobs in 'pending_review' status,
    ordered by match_score descending, then created_at descending.
    """
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM saved_jobs
            WHERE status = 'pending_review'
            ORDER BY match_score DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_job_by_hash(job_hash: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single job record from saved_jobs by job_hash.
    """
    if not job_hash:
        return None
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM saved_jobs WHERE job_hash = ? LIMIT 1", (job_hash,))
        row = cursor.fetchone()
        return dict(row) if row else None


class JobMemory:
    """Convenience class wrapper exposing all storage utilities."""
    generate_job_hash = staticmethod(generate_job_hash)
    is_job_saved = staticmethod(is_job_saved)
    save_discovered_job = staticmethod(save_discovered_job)
    update_job_assets = staticmethod(update_job_assets)
    mark_job_status = staticmethod(mark_job_status)
    get_pending_jobs = staticmethod(get_pending_jobs)
    get_job_by_hash = staticmethod(get_job_by_hash)
    init_db = staticmethod(init_db)
