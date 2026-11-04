# Claude-Mem Observation Audit

[简体中文](README.zh-CN.md)

A tool call can be recorded before it is linked to a memory observation. When you are investigating a worker restart or quota cooldown, it helps to see which rows are still unlinked—and how old they are.

Claude-Mem Observation Audit is a small, read-only Python CLI for that one check. It counts tool_uses rows with a NULL observation_id, separates recent rows from older review candidates, and keeps session details opt-in.

It does not decide that data was lost. An unlinked row can be intentional or still processing.

## Try it first

~~~bash
python3 claude_mem_audit.py --demo
~~~

The demo uses a synthetic in-memory database. It does not open your Claude-Mem files.

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

## What it checks

- Counts all rows in tool_uses.
- Counts rows with and without an observation_id.
- Separates recent unlinked rows from older review candidates.
- Optionally lists the session groups and project names for older rows.
- Stops if the expected table or required columns are missing.

It opens SQLite with mode=ro and issues schema reads and aggregate SELECT queries. It never selects tool input, tool response, or prompt columns, and it does not send data over the network.

## What it does not claim

- An old unlinked row is not proof of a lost memory.
- This tool does not recover, resend, delete, or modify anything.
- It does not inspect worker health or reconstruct the processing queue.
- It does not parse logs. A separate parked-batch log counter was shared in [Claude-Mem issue #4737](https://github.com/thedotmack/claude-mem/issues/4737); this project focuses on the SQLite link state.
- It expects the tool_uses structure used by Claude-Mem v15.9.0. If the schema changes, it stops rather than guessing.

## Why this check

Users have reported observations left unlinked after quota cooldowns and worker restarts in [issue #4580](https://github.com/thedotmack/claude-mem/issues/4580). A separate discussion in [issue #4737](https://github.com/thedotmack/claude-mem/issues/4737) describes parked batches and recovery limits. Claude-Mem's v15.9.0 [doctor command](https://github.com/thedotmack/claude-mem/blob/v15.9.0/src/npx-cli/commands/doctor.ts) checks installation and worker health; it does not query tool_uses.observation_id.

This CLI makes the database relationship visible without reading the stored tool content.

## Preview status and feedback

The synthetic demo has been run on macOS with Python 3.9. Compatibility with real user databases has not yet been independently confirmed. If you try it, report the Claude-Mem version, operating system, Python version, and any schema error in [Issues](../../issues).

Please do not attach a database, worker log, prompt, tool input, or tool response to an issue.

## Scope

- Python standard library only.
- Independent community utility; not affiliated with the Claude-Mem maintainers.
- MIT licensed.
