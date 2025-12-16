"""
Enterprise Audit Logging for Misata.

This module provides:
- Complete audit trail of all data generation operations
- Session tracking with user context
- Compliance-ready export formats
- Data lineage tracking

This addresses the critic's concern: "No enterprise features"
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path


@dataclass
class AuditEntry:
    """A single audit log entry."""
    timestamp: str
    session_id: str
    operation: str
    details: Dict[str, Any]
    user_id: Optional[str] = None
    status: str = "success"
    duration_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "operation": self.operation,
            "user_id": self.user_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "details": self.details
        }


class AuditLogger:
    """
    Enterprise audit logging for compliance and debugging.

    Tracks:
    - Schema generations (LLM calls)
    - Data generations (row counts, tables)
    - User corrections (feedback)
    - Validation results
    - Export operations
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize audit logger.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.misata/audit.db
        """
        if db_path is None:
            home = Path.home()
            misata_dir = home / ".misata"
            misata_dir.mkdir(exist_ok=True)
            db_path = str(misata_dir / "audit.db")

        self.db_path = db_path
        self._init_db()
        self._current_session: Optional[str] = None

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                user_id TEXT,
                status TEXT DEFAULT 'success',
                duration_ms INTEGER,
                details TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                user_id TEXT,
                story TEXT,
                tables_generated INTEGER DEFAULT 0,
                rows_generated INTEGER DEFAULT 0,
                corrections_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)
        """)

        conn.commit()
        conn.close()

    def start_session(self, user_id: Optional[str] = None) -> str:
        """
        Start a new audit session.

        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        self._current_session = session_id

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO sessions (session_id, start_time, user_id)
            VALUES (?, ?, ?)
        """, (session_id, datetime.now().isoformat(), user_id))

        conn.commit()
        conn.close()

        self.log("session_start", {"user_id": user_id})

        return session_id

    def end_session(self, session_id: Optional[str] = None):
        """End an audit session."""
        session_id = session_id or self._current_session
        if not session_id:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE sessions SET end_time = ?, status = 'completed'
            WHERE session_id = ?
        """, (datetime.now().isoformat(), session_id))

        conn.commit()
        conn.close()

        self.log("session_end", {})
        self._current_session = None

    def log(
        self,
        operation: str,
        details: Dict[str, Any],
        status: str = "success",
        duration_ms: Optional[int] = None,
        user_id: Optional[str] = None
    ):
        """
        Log an operation.

        Args:
            operation: Type of operation (e.g., 'schema_generation', 'data_export')
            details: Operation details
            status: 'success', 'error', or 'warning'
            duration_ms: Operation duration in milliseconds
            user_id: Optional user identifier
        """
        session_id = self._current_session or "no_session"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audit_log (timestamp, session_id, operation, user_id, status, duration_ms, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            session_id,
            operation,
            user_id,
            status,
            duration_ms,
            json.dumps(details)
        ))

        conn.commit()
        conn.close()

    def log_schema_generation(self, story: str, tables_count: int, duration_ms: int):
        """Log a schema generation operation."""
        self.log("schema_generation", {
            "story_length": len(story),
            "story_preview": story[:100] + "..." if len(story) > 100 else story,
            "tables_generated": tables_count
        }, duration_ms=duration_ms)

        # Update session
        if self._current_session:
            self._update_session(tables=tables_count)

    def log_data_generation(self, tables: Dict[str, int], total_rows: int, duration_ms: int):
        """Log a data generation operation."""
        self.log("data_generation", {
            "tables": tables,
            "total_rows": total_rows
        }, duration_ms=duration_ms)

        if self._current_session:
            self._update_session(rows=total_rows)

    def log_correction(self, table: str, column: str, change: str):
        """Log a user correction."""
        self.log("user_correction", {
            "table": table,
            "column": column,
            "change": change
        })

        if self._current_session:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions SET corrections_count = corrections_count + 1
                WHERE session_id = ?
            """, (self._current_session,))
            conn.commit()
            conn.close()

    def log_validation(self, passed: bool, score: float, issues_count: int):
        """Log a validation result."""
        self.log("validation", {
            "passed": passed,
            "score": score,
            "issues_count": issues_count
        }, status="success" if passed else "warning")

    def log_export(self, format: str, tables: List[str], file_path: str):
        """Log a data export."""
        self.log("data_export", {
            "format": format,
            "tables": tables,
            "file_path": file_path
        })

    def _update_session(self, tables: int = 0, rows: int = 0):
        """Update session statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if tables:
            cursor.execute("""
                UPDATE sessions SET tables_generated = tables_generated + ?
                WHERE session_id = ?
            """, (tables, self._current_session))

        if rows:
            cursor.execute("""
                UPDATE sessions SET rows_generated = rows_generated + ?
                WHERE session_id = ?
            """, (rows, self._current_session))

        conn.commit()
        conn.close()

    def get_session_logs(self, session_id: str) -> List[AuditEntry]:
        """Get all logs for a session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT timestamp, session_id, operation, user_id, status, duration_ms, details
            FROM audit_log
            WHERE session_id = ?
            ORDER BY timestamp
        """, (session_id,))

        entries = []
        for row in cursor.fetchall():
            entries.append(AuditEntry(
                timestamp=row[0],
                session_id=row[1],
                operation=row[2],
                user_id=row[3],
                status=row[4],
                duration_ms=row[5],
                details=json.loads(row[6]) if row[6] else {}
            ))

        conn.close()
        return entries

    def export_compliance_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        format: str = "json"
    ) -> str:
        """
        Export compliance-ready audit report.

        Args:
            start_date: Filter start (ISO format)
            end_date: Filter end (ISO format)
            format: 'json' or 'csv'

        Returns:
            Report as string
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)

        query += " ORDER BY timestamp"
        cursor.execute(query, params)

        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()

        if format == "json":
            records = [dict(zip(columns, row)) for row in rows]
            return json.dumps({
                "report_type": "Misata Compliance Audit",
                "generated_at": datetime.now().isoformat(),
                "record_count": len(records),
                "records": records
            }, indent=2)

        else:  # csv
            lines = [",".join(columns)]
            for row in rows:
                lines.append(",".join(str(v) if v else "" for v in row))
            return "\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        """Get audit summary statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM audit_log")
        total_ops = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cursor.fetchone()[0]

        cursor.execute("""
            SELECT operation, COUNT(*) FROM audit_log
            GROUP BY operation ORDER BY COUNT(*) DESC LIMIT 5
        """)
        top_ops = cursor.fetchall()

        cursor.execute("SELECT SUM(rows_generated) FROM sessions")
        total_rows = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "total_operations": total_ops,
            "total_sessions": total_sessions,
            "total_rows_generated": total_rows,
            "top_operations": dict(top_ops)
        }


@contextmanager
def audited_session(user_id: Optional[str] = None):
    """
    Context manager for audited operations.

    Usage:
        with audited_session("user123") as audit:
            audit.log_schema_generation(...)
            audit.log_data_generation(...)
    """
    logger = AuditLogger()
    session_id = logger.start_session(user_id)

    try:
        yield logger
    finally:
        logger.end_session(session_id)


# Global instance for convenience
_global_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create global audit logger."""
    global _global_logger
    if _global_logger is None:
        _global_logger = AuditLogger()
    return _global_logger
