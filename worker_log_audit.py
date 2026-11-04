"""Read-only aggregate audit of documented Claude-Mem worker log markers."""

from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from itertools import chain
from pathlib import Path
import re
from typing import Iterable


PARKED_BATCH_RE = re.compile(
    r"Batch parked\b.*?parkedMessageIds=\[([0-9,\s]*)\].*?paidSendsSpent=(\d+)"
)
SESSION_END_DROP_RE = re.compile(
    r"Session ended with parked batches; they were never resent\b"
)


class WorkerLogAuditError(Exception):
    """A selected worker log could not be read safely."""


def audit_worker_stream(lines: Iterable[str], sources: list[str]) -> dict[str, object]:
    line_count = 0
    recognized_line_count = 0
    parked_batch_events = 0
    session_end_drop_lines = 0
    message_ids: Counter[str] = Counter()
    paid_sends_spent: Counter[str] = Counter()

    for line in lines:
        line_count += 1
        parked = PARKED_BATCH_RE.search(line)
        session_end_drop = SESSION_END_DROP_RE.search(line)
        if parked or session_end_drop:
            recognized_line_count += 1
        if parked:
            parked_batch_events += 1
            paid_sends_spent[parked.group(2)] += 1
            message_ids.update(re.findall(r"\d+", parked.group(1)))
        if session_end_drop:
            session_end_drop_lines += 1

    return {
        "log_files_scanned": len(sources),
        "read_only": True,
        "lines_scanned": line_count,
        "recognized_lines": recognized_line_count,
        "parked_batch_events": parked_batch_events,
        "parked_message_id_occurrences": sum(message_ids.values()),
        "distinct_parked_message_ids": len(message_ids),
        "message_ids_repeated_in_log": sum(
            1 for occurrences in message_ids.values() if occurrences > 1
        ),
        "paid_sends_spent_events": dict(
            sorted(paid_sends_spent.items(), key=lambda item: int(item[0]))
        ),
        "session_end_drop_lines": session_end_drop_lines,
        "recognized_format": recognized_line_count > 0,
    }


def audit_worker_logs(paths: list[Path]) -> dict[str, object]:
    if not paths:
        raise WorkerLogAuditError("Select at least one worker log.")

    resolved: list[Path] = []
    for path in paths:
        candidate = path.expanduser()
        if not candidate.is_file():
            raise WorkerLogAuditError(f"Worker log file not found: {candidate.name}")
        resolved.append(candidate)

    try:
        with ExitStack() as stack:
            streams = [
                stack.enter_context(
                    path.open("r", encoding="utf-8", errors="replace")
                )
                for path in resolved
            ]
            return audit_worker_stream(
                chain.from_iterable(streams), [path.name for path in resolved]
            )
    except OSError as error:
        raise WorkerLogAuditError(
            f"Could not read a selected worker log ({error})."
        ) from error
