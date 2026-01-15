"""
Human-in-the-Loop Feedback System for Misata.

This module provides:
- Schema correction collection and storage
- Learning from user feedback to improve future generations
- Persistent feedback database (SQLite)
- Feedback-aware prompt enhancement

This addresses the critic's concern: "No learning/feedback loop"
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path


@dataclass
class SchemaCorrection:
    """A single schema correction from user feedback."""
    original_column: Dict[str, Any]
    corrected_column: Dict[str, Any]
    table_name: str
    reason: str
    timestamp: str
    story_context: Optional[str] = None


@dataclass
class FeedbackStats:
    """Statistics about collected feedback."""
    total_corrections: int
    unique_patterns: int
    most_common_fixes: List[Tuple[str, int]]
    columns_corrected: int
    tables_affected: int


class FeedbackDatabase:
    """
    Persistent storage for user feedback using SQLite.

    Stores schema corrections that can be used to:
    1. Improve prompts over time
    2. Auto-fix common mistakes
    3. Learn industry-specific patterns
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize feedback database.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.misata/feedback.db
        """
        if db_path is None:
            home = Path.home()
            misata_dir = home / ".misata"
            misata_dir.mkdir(exist_ok=True)
            db_path = str(misata_dir / "feedback.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Corrections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                original_type TEXT,
                corrected_type TEXT,
                original_params TEXT,
                corrected_params TEXT,
                reason TEXT,
                story_context TEXT,
                industry TEXT
            )
        """)

        # Patterns table for learned rules
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                pattern_value TEXT NOT NULL,
                confidence REAL,
                occurrence_count INTEGER DEFAULT 1,
                last_updated TEXT
            )
        """)

        # Sessions table for audit logging
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                story TEXT,
                schema_generated TEXT,
                tables_count INTEGER,
                rows_generated INTEGER,
                corrections_made INTEGER DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

    def add_correction(
        self,
        table_name: str,
        column_name: str,
        original: Dict[str, Any],
        corrected: Dict[str, Any],
        reason: str = "",
        story_context: str = "",
        industry: str = ""
    ) -> int:
        """
        Store a schema correction.

        Args:
            table_name: Name of the table
            column_name: Name of the corrected column
            original: Original column definition from LLM
            corrected: User's corrected definition
            reason: Why the correction was made
            story_context: Original story that generated this
            industry: Industry context (saas, healthcare, etc.)

        Returns:
            ID of the inserted correction
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO corrections (
                timestamp, table_name, column_name,
                original_type, corrected_type,
                original_params, corrected_params,
                reason, story_context, industry
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            table_name,
            column_name,
            original.get("type"),
            corrected.get("type"),
            json.dumps(original.get("distribution_params", {})),
            json.dumps(corrected.get("distribution_params", {})),
            reason,
            story_context,
            industry
        ))

        correction_id = cursor.lastrowid

        # Update learned patterns
        self._update_patterns(cursor, column_name, original, corrected)

        conn.commit()
        conn.close()

        return correction_id

    def _update_patterns(
        self,
        cursor: sqlite3.Cursor,
        column_name: str,
        original: Dict,
        corrected: Dict
    ):
        """Learn patterns from corrections."""
        # Pattern: column name -> correct type
        pattern_key = column_name.lower()
        pattern_value = json.dumps({
            "type": corrected.get("type"),
            "params": corrected.get("distribution_params", {})
        })

        # Check if pattern exists
        cursor.execute("""
            SELECT id, occurrence_count FROM patterns
            WHERE pattern_type = 'column_name' AND pattern_key = ?
        """, (pattern_key,))

        existing = cursor.fetchone()

        if existing:
            # Update occurrence count
            cursor.execute("""
                UPDATE patterns
                SET occurrence_count = occurrence_count + 1,
                    pattern_value = ?,
                    last_updated = ?
                WHERE id = ?
            """, (pattern_value, datetime.now().isoformat(), existing[0]))
        else:
            # Insert new pattern
            cursor.execute("""
                INSERT INTO patterns (
                    pattern_type, pattern_key, pattern_value,
                    confidence, last_updated
                ) VALUES (?, ?, ?, ?, ?)
            """, ('column_name', pattern_key, pattern_value, 0.5, datetime.now().isoformat()))

    def get_learned_patterns(self, min_occurrences: int = 2) -> Dict[str, Dict]:
        """
        Get patterns learned from corrections.

        Args:
            min_occurrences: Minimum times a pattern was seen

        Returns:
            Dict mapping column names to suggested configurations
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pattern_key, pattern_value, occurrence_count
            FROM patterns
            WHERE pattern_type = 'column_name' AND occurrence_count >= ?
            ORDER BY occurrence_count DESC
        """, (min_occurrences,))

        patterns = {}
        for key, value, count in cursor.fetchall():
            patterns[key] = {
                "suggestion": json.loads(value),
                "confidence": min(0.9, 0.5 + count * 0.1),
                "occurrences": count
            }

        conn.close()
        return patterns

    def get_stats(self) -> FeedbackStats:
        """Get statistics about collected feedback."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total corrections
        cursor.execute("SELECT COUNT(*) FROM corrections")
        total = cursor.fetchone()[0]

        # Unique patterns
        cursor.execute("SELECT COUNT(DISTINCT pattern_key) FROM patterns")
        patterns = cursor.fetchone()[0]

        # Most common column fixes
        cursor.execute("""
            SELECT column_name, COUNT(*) as cnt
            FROM corrections
            GROUP BY column_name
            ORDER BY cnt DESC
            LIMIT 5
        """)
        common_fixes = cursor.fetchall()

        # Unique columns
        cursor.execute("SELECT COUNT(DISTINCT column_name) FROM corrections")
        unique_cols = cursor.fetchone()[0]

        # Unique tables
        cursor.execute("SELECT COUNT(DISTINCT table_name) FROM corrections")
        unique_tables = cursor.fetchone()[0]

        conn.close()

        return FeedbackStats(
            total_corrections=total,
            unique_patterns=patterns,
            most_common_fixes=common_fixes,
            columns_corrected=unique_cols,
            tables_affected=unique_tables
        )

    def generate_prompt_enhancement(self) -> str:
        """
        Generate prompt enhancement based on learned corrections.

        This is injected into the LLM prompt to improve future generations.
        """
        patterns = self.get_learned_patterns(min_occurrences=1)

        if not patterns:
            return ""

        lines = [
            "Based on previous user corrections, apply these rules:",
            ""
        ]

        for col_name, data in list(patterns.items())[:10]:
            suggestion = data["suggestion"]
            data["confidence"]

            lines.append(f"- Column '{col_name}': use type '{suggestion.get('type')}' with params {suggestion.get('params')}")

        return "\n".join(lines)


class HumanFeedbackLoop:
    """
    Main interface for human-in-the-loop feedback.

    Provides methods to:
    1. Collect corrections from users
    2. Apply learned patterns to new schemas
    3. Generate enhanced prompts
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db = FeedbackDatabase(db_path)

    def submit_correction(
        self,
        table_name: str,
        column_name: str,
        original: Dict[str, Any],
        corrected: Dict[str, Any],
        reason: str = "",
        context: str = ""
    ) -> Dict[str, Any]:
        """
        Submit a schema correction.

        Returns confirmation with learned pattern info.
        """
        correction_id = self.db.add_correction(
            table_name=table_name,
            column_name=column_name,
            original=original,
            corrected=corrected,
            reason=reason,
            story_context=context
        )

        return {
            "id": correction_id,
            "message": "Correction recorded. Misata will learn from this.",
            "pattern_learned": column_name.lower()
        }

    def apply_learned_patterns(
        self,
        schema: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Apply learned patterns to improve a schema.

        Args:
            schema: Schema to enhance

        Returns:
            (enhanced_schema, list of changes made)
        """
        patterns = self.db.get_learned_patterns()
        changes = []

        columns = schema.get("columns", {})

        for table_name, cols in columns.items():
            for i, col in enumerate(cols):
                col_name = col.get("name", "").lower()

                if col_name in patterns:
                    pattern = patterns[col_name]
                    if pattern["confidence"] > 0.6:
                        suggestion = pattern["suggestion"]

                        # Apply correction
                        old_type = col.get("type")
                        new_type = suggestion.get("type")

                        if old_type != new_type:
                            columns[table_name][i]["type"] = new_type
                            columns[table_name][i]["distribution_params"] = suggestion.get("params", {})
                            changes.append(
                                f"Applied learned pattern to {table_name}.{col['name']}: "
                                f"{old_type} -> {new_type} (confidence: {pattern['confidence']:.0%})"
                            )

        schema["columns"] = columns
        return schema, changes

    def get_enhanced_prompt(self) -> str:
        """Get prompt enhancement from learned patterns."""
        return self.db.generate_prompt_enhancement()

    def get_feedback_report(self) -> str:
        """Get a summary of feedback collected."""
        stats = self.db.get_stats()

        lines = [
            "=" * 50,
            "MISATA FEEDBACK LEARNING REPORT",
            "=" * 50,
            f"Total Corrections Collected: {stats.total_corrections}",
            f"Patterns Learned: {stats.unique_patterns}",
            f"Columns Improved: {stats.columns_corrected}",
            f"Tables Affected: {stats.tables_affected}",
            "",
            "Most Common Corrections:"
        ]

        for col, count in stats.most_common_fixes:
            lines.append(f"  - {col}: {count} corrections")

        lines.append("=" * 50)

        return "\n".join(lines)


# Convenience function for CLI
def collect_feedback_interactive():
    """Interactive feedback collection (for CLI use)."""
    loop = HumanFeedbackLoop()
    print(loop.get_feedback_report())
