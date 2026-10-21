# SQLite Query activity

The desktop engine includes **Query SQLite Database** for reading an approved local `.db`, `.sqlite`, or `.sqlite3` file. It returns query rows as JSON-compatible objects for later workflow activities.

## Configure

- **Path**: project-relative by default; absolute paths are accepted only inside the project folder or an explicitly approved extra file root.
- **Query**: one SQL statement. The authorizer allows read-only `SELECT` and common table-expression queries. Writes, schema changes, `PRAGMA`, `ATTACH`, temporary-database access, and multiple statements are rejected.
- **Parameters**: a positional list or named mapping bound through SQLite parameters (`?` or `:name`). Use `{{ expression }}` to supply a list or mapping from workflow data. Values are never interpolated into the SQL string.
- **Result**: a variable name that receives an array of row objects. Duplicate column labels are preserved with deterministic `_2`, `_3` suffixes. BLOB values are represented as `{"$binaryBase64":"..."}`.
- **Maximum rows**: 1–100,000 (default 10,000). Results that exceed the cap fail; they are not silently truncated.
- **Timeout**: 1–120 seconds (default 30). SQLite's virtual-machine progress handler checks both the deadline and run cancellation. Database-lock waiting is capped at 500 ms.

The database file and serialized results are each bounded by the workflow `maxFileBytes` quota (20 MB by default; 100 MB hard maximum). Every query attempt and completion is written to the security audit history with an activity ID, relative approved-root path, parameter count and completed row count. SQL text and parameter values are not copied to the audit event.

The SQLite connection uses URI `mode=ro`, `query_only`, `trusted_schema=OFF`, and an authorizer allowlist. Extension loading stays disabled. Only the desktop engine can access the local database; the browser preview validates the activity but reports that it requires the desktop filesystem engine when run.

This activity does not connect to remote databases or provide a write, transaction, migration, or arbitrary extension interface. A SQLite file is still untrusted input: keep it inside approved roots and use the project file-size limit. Query results may contain sensitive information, so review destinations and permissions before subsequent workflow steps export or transmit them.
