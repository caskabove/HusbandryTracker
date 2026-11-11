# Morph/Genetics/Lineage are relational tables; schema changes apply themselves at startup

**Status**: accepted

**Context**: Adding Morph, Genetics and Lineage to Animal (see CONTEXT.md: Genetics, Gene, Gene
Catalog, Morph, Lineage) reopened the question ADR 0011 settled for sensor parameters: should the
schema go schemaless (a JSON column, generic key-value rows, or a document database) so new fields
stop needing migrations? On inspection, the pain wasn't SQL itself. `init_db()` already creates
new *tables* on every startup via `CREATE TABLE IF NOT EXISTS`. Only a new *column on an existing
table* needs a migration, and those were 26 hand-run `tools/migrate_*.py` scripts that nothing
tracked and that an installed copy never ran on upgrade.

**Decision**:

- **Relational tables** for the Gene Catalog, an Animal's Genetics, and Lineage Entries. A Lineage
  Entry is a row that either references a real Animal or holds a described parent, with its own
  parents as further Lineage Entry rows pointing back at it. SQLite's recursive queries walk the
  tree. This keeps real foreign keys (deleting Bob can't leave dangling references), and gives
  "every Animal carrying Clown" and future Pairing predictions proper indexed joins.
- **New morphs/genes are data, not schema.** The Gene Catalog is a user-editable table, so the most
  frequent change, a newly named morph, never touches the schema.
- **An automatic migration runner replaces hand-run scripts.** Numbered migrations live in the app,
  are tracked with `PRAGMA user_version`, and are applied at process startup (so on first launch
  after install or upgrade), taking a backup first, the same safety pattern the existing scripts
  already follow (see ADR 0019).

- **Existing databases**: the 26 `tools/migrate_*.py` scripts are ported into the runner as
  migrations 1–26. They're already idempotent, so every database (fresh install, partly migrated,
  or fully migrated) converges on the same version instead of being assumed current. This feature
  is migration 27.
- **A failed migration restores the pre-migration backup and the app refuses to start**, surfacing
  the error through the tray Supervisor. A half-migrated database is worse than a stopped app.

- **First release scope**: migration runner; Sex and a Knowledge Base species picker on Add/Edit
  Animal; Gene Catalog seeded for ball python, leopard gecko, crested gecko, gargoyle gecko,
  bearded dragon and corn snake; Genetics and Morph on the Animal; Lineage with link-or-describe
  parents, Copy Lineage, snapshot-on-delete; and an offspring list on a parent's Animal Page.
  Deferred: Pairing predictions, alleles, and Archived/Sold/Deceased Animals.

**Considered Options**:

- *JSON column on `animal`*: no migrations, but references to real Animals and catalog Genes become
  untyped IDs inside text, and gene queries and pairing math get clumsy.
- *Generic key-value / custom-field tables*: already rejected by ADR 0011; nothing has changed.
- *Document database*: contradicts ADR 0001's SQLite architecture, packaging, and backup/restore,
  and solves a problem the migration runner solves more cheaply.
- *End-user Custom Fields*: not requested. The pain was a developer one. If wanted later, a JSON
  column of user-defined values is the right tool for that separate feature.

**Found while implementing (RHA-101)**: `.gitignore` ignored `migrate*.py`, so only 6 of the 26
scripts were ever committed; the other 20 existed only on one development machine, and no
CI-built installer could have upgraded a database at all. The pattern is gone, and migrations now
live in `db/migrations/`, bundled into every exe.

**Consequences**: reaffirms ADR 0011's "real columns" stance and removes its main cost: a schema
change is still a migration, but one that ships with the release and applies itself. Whoever owns
the storage abstraction (RHA-22) inherits the runner as the SQLite backend's migration mechanism.
