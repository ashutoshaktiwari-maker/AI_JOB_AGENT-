"""
SQLite Database Access Layer for Application Tracker.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.models import ApplicationCreate, ApplicationStatus, ApplicationUpdate

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/applications.db")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _resolve_applications_db_path() -> Path:
    """Resolves applications.db path flexibly regardless of whether running from root or backend/."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "applications.db",
        Path("data/applications.db").resolve(),
        Path(__file__).resolve().parent.parent / "data" / "applications.db",
    ]
    for c in candidates:
        if c.exists():
            return c
    target = Path(__file__).resolve().parent.parent.parent / "data" / "applications.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


class Database:
    """Manages SQLite database connections and CRUD operations for applications."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else _resolve_applications_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns SQLite connection with dict-like row factory."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Executes schema.sql to ensure tables exist."""
        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            with self._get_connection() as conn:
                conn.executescript(schema_sql)
                conn.commit()

    def sync_from_agent_memory(self) -> int:
        """
        Synchronizes jobs applied or flagged by the Telegram / Autonomous Agent
        from backend/data/jobs_memory.db into applications.db.
        Ensures applications made via Telegram are immediately visible on the dashboard.
        """
        candidates = [
            Path(__file__).resolve().parent.parent / "data" / "jobs_memory.db",
            Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "jobs_memory.db",
            Path("backend/data/jobs_memory.db").resolve(),
            Path("data/jobs_memory.db").resolve(),
        ]
        mem_path = next((c for c in candidates if c.exists()), None)
        if not mem_path:
            return 0

        synced_count = 0
        try:
            mem_conn = sqlite3.connect(str(mem_path))
            mem_conn.row_factory = sqlite3.Row
            cursor = mem_conn.cursor()
            cursor.execute(
                """
                SELECT job_hash, title, company, location, portal, url,
                       description, match_score, status, tailored_resume_path,
                       cover_letter_path, created_at, applied_at
                FROM saved_jobs
                WHERE status IN ('applied', 'needs_manual_review')
                ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()
            mem_conn.close()

            with self._get_connection() as app_conn:
                app_cursor = app_conn.cursor()
                for r in rows:
                    url = (r["url"] or "").strip()
                    company = (r["company"] or "Unknown Company").strip()
                    role = (r["title"] or "Target Role").strip()
                    score = r["match_score"] or 0
                    j_status = r["status"]
                    applied_date_raw = r["applied_at"] or r["created_at"] or datetime.now().isoformat()
                    applied_date = applied_date_raw[:10] if len(applied_date_raw) >= 10 else datetime.now().strftime("%Y-%m-%d")

                    status_val = "Applied"
                    if j_status == "applied":
                        notes = f"Applied via Telegram Agent (Match Fit: {score}%)"
                    else:
                        notes = f"Needs Review / CAPTCHA (Telegram Agent, Fit: {score}%)"

                    # Check if already in applications table
                    if url:
                        app_cursor.execute("SELECT id, status FROM applications WHERE apply_url = ? LIMIT 1", (url,))
                    else:
                        app_cursor.execute("SELECT id, status FROM applications WHERE LOWER(company) = LOWER(?) AND LOWER(role) = LOWER(?) LIMIT 1", (company, role))

                    existing = app_cursor.fetchone()
                    if not existing:
                        now_str = datetime.now().isoformat()
                        app_cursor.execute(
                            """
                            INSERT INTO applications (
                                company, role, apply_url, resume_version, cover_letter_version,
                                status, applied_date, notes, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                company,
                                role,
                                url,
                                r["tailored_resume_path"],
                                r["cover_letter_path"],
                                status_val,
                                applied_date,
                                notes,
                                r["created_at"] or now_str,
                                r["applied_at"] or now_str,
                            ),
                        )
                        synced_count += 1
                app_conn.commit()
        except Exception as exc:
            logger.warning("Error syncing applications from agent memory: %s", exc)

        return synced_count

    def add_application(self, app_data: ApplicationCreate) -> Dict[str, Any]:
        """Inserts a new job application record."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO applications (
                    company, role, apply_url, resume_version, cover_letter_version,
                    status, applied_date, interview_date, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    app_data.company,
                    app_data.role,
                    app_data.apply_url,
                    app_data.resume_version,
                    app_data.cover_letter_version,
                    app_data.status.value if isinstance(app_data.status, ApplicationStatus) else str(app_data.status),
                    app_data.applied_date,
                    app_data.interview_date,
                    app_data.notes,
                    now,
                    now,
                ),
            )
            conn.commit()
            new_id = cursor.lastrowid
            return self.get_application_by_id(new_id)

    def get_application_by_id(self, app_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single application by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM applications WHERE id = ?", (app_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_applications(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists applications, automatically syncing from Telegram agent memory."""
        self.sync_from_agent_memory()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM applications WHERE LOWER(status) = LOWER(?) ORDER BY id DESC",
                    (status,),
                )
            else:
                cursor.execute("SELECT * FROM applications ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def update_application(self, app_id: int, updates: ApplicationUpdate) -> Optional[Dict[str, Any]]:
        """Updates status, interview date, or notes for an application."""
        current = self.get_application_by_id(app_id)
        if not current:
            return None

        update_dict = updates.model_dump(exclude_unset=True)
        if not update_dict:
            return current

        fields = []
        values = []
        for k, v in update_dict.items():
            if v is not None:
                val = v.value if isinstance(v, ApplicationStatus) else v
                fields.append(f"{k} = ?")
                values.append(val)

        fields.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(app_id)

        set_clause = ", ".join(fields)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE applications SET {set_clause} WHERE id = ?", values)
            conn.commit()
            return self.get_application_by_id(app_id)

    def delete_application(self, app_id: int) -> bool:
        """Deletes an application by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM applications WHERE id = ?", (app_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, int]:
        """Calculates breakdown metrics across application statuses, automatically syncing from Telegram agent memory."""
        self.sync_from_agent_memory()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as count FROM applications GROUP BY status")
            counts = {row["status"]: row["count"] for row in cursor.fetchall()}

            return {
                "total": sum(counts.values()),
                "applied": counts.get("Applied", 0),
                "interview": counts.get("Interview", 0),
                "rejected": counts.get("Rejected", 0),
                "offer": counts.get("Offer", 0),
            }


# Singleton database instance
db = Database()
