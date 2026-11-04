# Claude-Mem Observation Audit

[简体中文](README.zh-CN.md)

A queue-depth reading of zero may still leave a practical question: what happened to each captured tool event? When you are investigating a worker restart or quota cooldown, this CLI puts two read-only clues side by side: database link counts and selected worker-log markers.

Claude-Mem Observation Audit is a small, read-only Python CLI. It counts `tool_uses` rows with a NULL `observation_id`, separates recent rows from older review candidates, and can count documented parked-batch and session-end markers in worker logs. Session details remain opt-in.

It does not decide that data was lost. An unlinked row can be intentional or still processing.

## Quick start

~~~bash
git clone https://github.com/LydiaTools/claude-mem-observation-audit.git
cd claude-mem-observation-audit
python3 claude_mem_audit.py --demo
~~~

Requires Python 3.9 or newer. There are no third-party packages to install. The demo uses a synthetic in-memory database; it does not open your Claude-Mem files.

Example:

~~~text
Claude-Mem observation audit
Read-only · aggregate counts only unless session details are requested

Database: synthetic in-memory demo
Tool-use rows: 4
Linked: 1 · unlinked: 3 (recent: 1)
Older than 24h: 2 row(s) across 1 session(s)

Interpretation: older unlinked rows are review candidates, not proof of lost memory.
Recent unlinked rows may still be processing or may not produce an observation.
~~~

## Check a local database

The default Claude-Mem database path is:

~~~bash
python3 claude_mem_audit.py ~/.claude-mem/claude-mem.db
~~~

Set a different age threshold or database path when needed:

~~~bash
python3 claude_mem_audit.py /path/to/claude-mem.db --stale-hours 48
~~~

Session IDs and project names are hidden unless you ask for them:

~~~bash
python3 claude_mem_audit.py ~/.claude-mem/claude-mem.db --show-sessions --json
~~~

## Check selected worker logs

Count parked-batch markers in one log:

~~~bash
python3 claude_mem_audit.py --worker-log /path/to/worker.log
~~~

Pass rotated logs more than once, or combine the log scan with the database audit:

~~~bash
python3 claude_mem_audit.py --worker-log worker.log --worker-log worker.log.1
python3 claude_mem_audit.py ~/.claude-mem/claude-mem.db --worker-log worker.log --json
~~~

The log scan recognizes the documented `Batch parked` marker with `parkedMessageIds` and `paidSendsSpent`, plus `Session ended with parked batches; they were never resent`. It reports aggregate counts and does not print message IDs or raw log lines. If no supported marker is found, the report says so; zero matches do not mean zero incidents.

## What it checks

- Counts all rows in tool_uses.
- Counts rows with and without an observation_id.
- Separates recent unlinked rows from older review candidates.
- Optionally lists the session groups and project names for older rows.
- For selected worker logs, counts parked-batch events, message-ID occurrences/repeats, paid-send counts, and session-end drop markers.
- Stops if the expected table or required columns are missing.

It opens SQLite with mode=ro and issues schema reads and aggregate SELECT queries. It never selects tool input, tool response, or prompt columns, and it does not send data over the network.

## What it does not claim

- An old unlinked row is not proof of a lost memory.
- This tool does not recover, resend, delete, or modify anything.
- It does not inspect worker health or reconstruct the processing queue.
- A log marker is not proof that a database record is missing or recoverable. A log with no recognized markers is not proof that no queue event was lost.
- It expects the tool_uses structure used by Claude-Mem v15.9.0. If the schema changes, it stops rather than guessing.
- Log matching is limited to the documented 15.x message patterns above; it is not a complete worker-log parser.

## Why this check

Users have reported observations left unlinked after quota cooldowns and worker restarts in [issue #4580](https://github.com/thedotmack/claude-mem/issues/4580). In [issue #4737](https://github.com/thedotmack/claude-mem/issues/4737), users shared counts of parked batches and session-end drops, and discussed how a zero queue-depth reading can miss parked events. Claude-Mem's v15.9.0 [doctor command](https://github.com/thedotmack/claude-mem/blob/v15.9.0/src/npx-cli/commands/doctor.ts) checks installation and worker health; it does not query tool_uses.observation_id.

This CLI makes database and selected log evidence visible without reading stored tool content or sending local data over the network.

## Preview status and feedback

The synthetic database demo has been run on macOS with Python 3.9. The new log scan is an early preview based on public 15.x log markers; compatibility with every real database or log format has not been independently confirmed. If you try it, report the Claude-Mem version, operating system, Python version, and whether any markers were recognized in [Issues](https://github.com/LydiaTools/claude-mem-observation-audit/issues).

Please do not attach a database, worker log, prompt, tool input, or tool response to an issue.

## Scope

- Python standard library only.
- Independent community utility; not affiliated with the Claude-Mem maintainers.
- MIT licensed.
