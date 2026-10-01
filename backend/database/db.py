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


class Database:
    """Manages SQLite database connections and CRUD operations for applications."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
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
        """Lists applications, optionally filtered by status."""
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
        """Calculates breakdown metrics across application statuses."""
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
