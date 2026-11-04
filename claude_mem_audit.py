#!/usr/bin/env python3
"""Read-only audit for Claude-Mem observation links and worker log markers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any

from worker_log_audit import WorkerLogAuditError, audit_worker_logs

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
    if "worker_log_audit" in report:
        database_report = {
            key: value for key, value in report.items() if key != "worker_log_audit"
        }
        lines = (
            render_text(database_report).splitlines()
            if "tool_use_rows" in database_report
            else ["Claude-Mem queue log audit", "Read-only · aggregate counts only"]
        )
        log_report = report["worker_log_audit"]
        lines += [
            "",
            "Worker log audit",
            f"Log files scanned: {log_report['log_files_scanned']}",
            f"Lines scanned: {log_report['lines_scanned']}",
            f"Parked batch events: {log_report['parked_batch_events']}",
            (
                "Parked message IDs: "
                f"{log_report['distinct_parked_message_ids']} distinct across "
                f"{log_report['parked_message_id_occurrences']} occurrences"
            ),
            (
                "IDs repeated in selected logs: "
                f"{log_report['message_ids_repeated_in_log']}"
            ),
            (
                "Session-end 'never resent' markers: "
                f"{log_report['session_end_drop_lines']}"
            ),
            (
                "paidSendsSpent distribution: "
                + (
                    ", ".join(
                        f"{count} event(s) at {spent}"
                        for spent, count in log_report[
                            "paid_sends_spent_events"
                        ].items()
                    )
                    or "none"
                )
            ),
        ]
        if not log_report["recognized_format"]:
            lines.append(
                "No supported log markers matched; zero counts do not establish "
                "that no queue events were lost."
            )
        lines += [
            "",
            "Interpretation: log markers are review signals, not proof that a "
            "database record is missing or recoverable.",
            "Raw log lines and message IDs are not emitted.",
        ]
        if "checked_at_utc" in report:
            lines += ["", "Checked at UTC: " + report["checked_at_utc"]]
        return "\n".join(lines)

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
            "Read-only audit of Claude-Mem observation links and selected worker logs."
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
    parser.add_argument(
        "--worker-log",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="Read a selected worker log; repeat for rotated log files",
    )
    args = parser.parse_args()

    if args.stale_hours < 1:
        parser.error("--stale-hours must be at least 1")
    if args.demo and (args.database or args.worker_log):
        parser.error("--demo does not accept a database path or worker log")
    if not args.demo and not args.database and not args.worker_log:
        parser.error("provide a database path, --worker-log, or --demo")
    if args.show_sessions and not args.database and not args.demo:
        parser.error("--show-sessions requires a database path")

    try:
        if args.demo:
            report = demo_report(args.stale_hours, args.show_sessions)
        elif args.database:
            report = audit_database(
                args.database, args.stale_hours, args.show_sessions
            )
        else:
            report = {}
        if args.worker_log:
            report["worker_log_audit"] = audit_worker_logs(args.worker_log)
        report["checked_at_utc"] = now_utc()

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_text(report))
        return 0
    except (AuditError, WorkerLogAuditError) as error:
        print(f"Audit stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
