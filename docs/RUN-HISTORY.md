# Durable execution history

Studio stores run summaries, activity outcomes and bounded event records in a local SQLite WAL database. Run details are read through the local bridge and show the workflow SHA-256 used for the execution, recorded activity durations, saved events with storage timestamps, and any final error. The UI does not display the local project path.

When the application opens the history database, runs that were still marked `running` are changed to `interrupted`. This only establishes that Studio stopped before recording a terminal result. It cannot establish whether an HTTP request, UI action, file write or other external side effect completed. The detail panel calls this out and offers no resume or replay button. Inspect the destination system and then decide whether to start a new run manually.

Events are stored with a bounded per-event and per-run size. If the event quota is reached, history includes a truncation marker; a truncated timeline must not be treated as a complete record. Live debugger variables are excluded from saved debug-pause events. Run result persistence contains status, activity outcomes and errors, rather than the full runtime variable map.
