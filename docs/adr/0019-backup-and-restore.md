# Automatic + on-demand database Backup, and Supervisor-orchestrated Restore

**Status**: accepted

HerpMonitor needed a real answer to "I uninstalled and reinstalled — do I get my data back?" and
"my drive died — is my animal-care history gone?" ADR 0018 already made an uninstall leave `data/`
in place, which answers the first question for a reinstall to the same folder, but neither ADR
addressed drive failure, moving to a new machine, or protecting against an accidental `data/`
deletion. See CONTEXT.md: Backup, Restore.

**Decision**: everything durable lives in one file, `data/herpmonitor.db` (including Device
Registration's Tuya/Govee credentials, not just readings/history), so Backup is just a safe
point-in-time copy of that one file — via SQLite's Online Backup API (`sqlite3.Connection.backup()`),
not a plain filesystem copy, since a live-process copy risks capturing a half-written page mid-commit.

**Backup runs automatically once a day, plus on demand.** Ingest already owns the database and
already runs a continuous loop (`ingest/ingest.py`'s `main()`), so it's the one process responsible
for deciding *when* to back up — once per day, and immediately when it notices
`data/backup_requested`, a trigger file the Supervisor's "Back Up Now" tray item touches. This
keeps the Supervisor from ever needing to open the database itself, matching its existing
"never touches the database" boundary (ADR 0015) and reusing the same filesystem-contract shape
Command/Outbox already established (ADR 0014) — a Supervisor-to-Ingest signal is a smaller version
of the same idea, without needing a schema-validated envelope since it's an internal Core-to-Core
signal, not a Plugin-facing one. Backups older than 14 days are pruned on each automatic run.

**Restore is the one exception, and lives in the Supervisor.** Swapping the live database file
requires every process that could have it open (Web, Ingest) to be stopped first — something only
the Supervisor can guarantee, since it's the one thing that starts/stops them. Restore is
implemented there as `stop_all()` → safety-copy the current database as its own Backup → plain file
copy of the chosen Backup over `data/herpmonitor.db` → `start_all()`, behind a native Windows
Yes/No confirmation dialog (shelled out to PowerShell's `System.Windows.Forms.MessageBox`, the same
pattern already used for shortcut creation). This is still not "the Supervisor touching the
database" in the sense the original boundary cared about (no query, no open connection) — it's a
process-lifecycle operation that happens to end in a file copy while the database is guaranteed
closed by everyone.

**Considered and rejected**: a user-configurable backup destination (external drive, synced cloud
folder) — deferred. `data/backups/` inside the install folder is the default and only option for
now; a Backup file is a plain, single `.db` file the user can already copy anywhere else by hand
(File Explorer, or scripting it themselves) for real off-machine protection. Building destination
configuration into the app is real added scope (a settings field, path validation, handling a
missing/unplugged drive) versus a file a user can already act on manually.

**Consequences**: new `db.backup_database()` (mechanism), `ingest.ingest._run_backup_check()`
(policy — daily + on-demand + retention), and `tray/supervisor.py`'s "Back Up Now"/"Restore from
Backup" tray items. `data/backups/` and `data/backup_requested` are new, already covered by the
existing blanket `data/` gitignore rule. Not built here: configurable backup destinations, and any
backup format other than a raw SQLite file (e.g. compressed archives) — the file is small enough at
this app's scale that neither seemed worth the complexity yet.
