#!/usr/bin/env python3
"""Read-only audit for Claude-Mem tool-use rows without observation links."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any


REQUIRED_COLUMNS = {
    "content_session_id",
    "created_at_epoch",
    "observation_id",
}
OPTIONAL_COLUMNS = {"platform_source", "project", "session_db_id"}


class AuditError(Exception):
    """An input could not be safely inspected."""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def epoch_ms_to_utc(value: int | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).replace(
            microsecond=0
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def query_database(
    connection: sqlite3.Connection,
    label: str,
    stale_hours: int,
    show_sessions: bool,
) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if "tool_uses" not in tables:
        raise AuditError("The database has no tool_uses table; no schema was guessed.")

    columns = {
        row["name"]
        for row in connection.execute('PRAGMA table_info("tool_uses")')
    }
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise AuditError(
            "The tool_uses table is missing required columns: " + ", ".join(missing)
        )

    cutoff_ms = int(time.time() * 1000) - stale_hours * 60 * 60 * 1000
    total = connection.execute("SELECT COUNT(*) FROM tool_uses").fetchone()[0]
    unlinked = connection.execute(
        "SELECT COUNT(*) FROM tool_uses WHERE observation_id IS NULL"
    ).fetchone()[0]
    stale = connection.execute(
        """SELECT COUNT(*) FROM tool_uses
           WHERE observation_id IS NULL AND created_at_epoch <= ?""",
        (cutoff_ms,),
    ).fetchone()[0]

    stale_sessions = connection.execute(
        """SELECT COUNT(DISTINCT content_session_id) FROM tool_uses
           WHERE observation_id IS NULL AND created_at_epoch <= ?""",
        (cutoff_ms,),
    ).fetchone()[0]

    session_details: list[dict[str, Any]] = []
    if show_sessions:
        optional_expr = {
            name: f'"{name}"' if name in columns else "NULL"
            for name in OPTIONAL_COLUMNS
        }
        groups = connection.execute(
            f"""SELECT content_session_id,
                       {optional_expr['project']} AS project,
                       {optional_expr['platform_source']} AS platform_source,
                       {optional_expr['session_db_id']} AS session_db_id,
                       COUNT(*) AS unlinked_rows,
                       MIN(created_at_epoch) AS oldest_epoch,
                       MAX(created_at_epoch) AS newest_epoch
                FROM tool_uses
                WHERE observation_id IS NULL AND created_at_epoch <= ?
                GROUP BY content_session_id, project, platform_source, session_db_id
                ORDER BY oldest_epoch ASC""",
            (cutoff_ms,),
        ).fetchall()
        session_details = [
            {
                "content_session_id": row["content_session_id"],
                "session_db_id": row["session_db_id"],
                "project": row["project"],
                "platform_source": row["platform_source"],
                "unlinked_rows": row["unlinked_rows"],
                "oldest_utc": epoch_ms_to_utc(row["oldest_epoch"]),
                "newest_utc": epoch_ms_to_utc(row["newest_epoch"]),
            }
            for row in groups
        ]

    return {
        "source": label,
        "read_only": True,
        "schema_checked": True,
        "stale_threshold_hours": stale_hours,
        "tool_use_rows": total,
        "linked_rows": total - unlinked,
        "unlinked_rows": unlinked,
        "recent_unlinked_rows": unlinked - stale,
        "stale_unlinked_rows": stale,
        "stale_unlinked_sessions": stale_sessions,
        "session_details": session_details,
    }


def audit_database(path: Path, stale_hours: int, show_sessions: bool) -> dict[str, Any]:
    path = path.expanduser()
    if not path.is_file():
        raise AuditError("Database file not found.")

    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=3)
    except sqlite3.Error as error:
        raise AuditError(f"Could not open the database read-only ({error}).") from error
    try:
        return query_database(connection, path.name, stale_hours, show_sessions)
    except sqlite3.Error as error:
        raise AuditError(f"SQLite could not read the database ({error}).") from error
    finally:
        connection.close()


def demo_report(stale_hours: int, show_sessions: bool) -> dict[str, Any]:
    connection = sqlite3.connect(":memory:")
    now_ms = int(time.time() * 1000)
    old_ms = now_ms - (stale_hours + 24) * 60 * 60 * 1000
    recent_ms = now_ms - 10 * 60 * 1000
    connection.execute(
        """CREATE TABLE tool_uses (
            id INTEGER PRIMARY KEY,
            content_session_id TEXT NOT NULL,
            session_db_id INTEGER,
            project TEXT NOT NULL,
            platform_source TEXT NOT NULL,
            observation_id INTEGER,
            created_at_epoch INTEGER NOT NULL
        )"""
    )
    connection.executemany(
        """INSERT INTO tool_uses
           (content_session_id, session_db_id, project, platform_source,
            observation_id, created_at_epoch)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            ("demo-session-a", 1, "sample", "claude", 10, old_ms),
            ("demo-session-a", 1, "sample", "claude", None, old_ms),
            ("demo-session-a", 1, "sample", "claude", None, old_ms),
            ("demo-session-b", 2, "sample", "codex", None, recent_ms),
        ],
    )
    try:
        report = query_database(
            connection, "synthetic in-memory demo", stale_hours, show_sessions
        )
    finally:
        connection.close()
    report["demo_data"] = "Synthetic rows only; no local database was opened."
    return report


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "Claude-Mem observation audit",
        "Read-only · aggregate counts only unless session details are requested",
        "",
        f"Database: {report['source']}",
        f"Tool-use rows: {report['tool_use_rows']}",
        (
            f"Linked: {report['linked_rows']} · "
            f"unlinked: {report['unlinked_rows']} "
            f"(recent: {report['recent_unlinked_rows']})"
        ),
        (
            f"Older than {report['stale_threshold_hours']}h: "
            f"{report['stale_unlinked_rows']} row(s) across "
            f"{report['stale_unlinked_sessions']} session(s)"
        ),
    ]
    if report["session_details"]:
        lines.append("Stale session groups:")
        for item in report["session_details"]:
            lines.append(
                f"  {item['content_session_id']} · "
                f"{item['project'] or 'unknown project'} · "
                f"{item['unlinked_rows']} row(s) · oldest {item['oldest_utc']}"
            )
    lines += [
        "",
        "Interpretation: older unlinked rows are review candidates, not proof of lost memory.",
        "Recent unlinked rows may still be processing or may not produce an observation.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only counts of Claude-Mem tool-use rows with no linked observation."
        )
    )
    parser.add_argument(
        "database", nargs="?", type=Path, help="Claude-Mem SQLite database"
    )
    parser.add_argument(
        "--stale-hours",
        type=int,
        default=24,
        help="Age threshold for review candidates (default: 24)",
    )
    parser.add_argument(
        "--show-sessions",
        action="store_true",
        help="Include session IDs and project details in the output",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead")
    parser.add_argument(
        "--demo", action="store_true", help="Run a synthetic in-memory example"
    )
    args = parser.parse_args()

    if args.stale_hours < 1:
        parser.error("--stale-hours must be at least 1")
    if args.demo and args.database:
        parser.error("--demo does not accept a database path")
    if not args.demo and not args.database:
        parser.error("provide a database path or --demo")

    try:
        if args.demo:
            report = demo_report(args.stale_hours, args.show_sessions)
        else:
            report = audit_database(
                args.database, args.stale_hours, args.show_sessions
            )
        report["checked_at_utc"] = now_utc()

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_text(report))
        return 0
    except AuditError as error:
        print(f"Audit stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
