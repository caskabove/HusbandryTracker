# Rename HerpMonitor to Husbandry Tracker before first release

**Status**: accepted (recorded retroactively 2026-10-16; the rename landed in commit b9385a3, 2026-09-28)

The app shipped internally as "HerpMonitor", and the working public name had been "Herp Tracker".
"Herp Tracker" collides with an existing competitor app (HerpTracker), and "herp" undersells the
product, which also suits amphibian, invertebrate and aquatic keepers. No installer had shipped yet,
so this was the last point at which a rename cost nothing for users.

**Decision**: the product is **Husbandry Tracker**, published by **CaskAbove**.

- In the running app (UI, page titles, tray tooltip, installer display name) the product calls
  itself only "Husbandry Tracker". CaskAbove is the publisher — the installer's publisher field,
  the `LICENSE` copyright holder, the GitHub organization and the website — not part of the in-app
  name.
- Code, packaging and paths use `husbandrytracker`: `packaging/husbandrytracker.spec`,
  `packaging/husbandrytracker.iss`, `HusbandryTrackerSupervisor.exe`, and the database file
  `data/husbandrytracker.db`.
- The Inno Setup `AppId` GUID was reissued at the rename (safe because no installer had shipped)
  and must now stay stable across releases so upgrades install in place.
- ADRs written before the rename keep "HerpMonitor" in their prose. That is the original wording,
  left as written, not a missed rename.

**Consequences**:

- There is no automatic migration from the old database name. Any pre-rename development install
  must rename `data/herpmonitor.db` to `data/husbandrytracker.db` by hand (one-off migration
  scripts in `tools/` that predate the rename still mention the old name in their docstrings).
- The website (caskabove.com) and any marketing copy must use "Husbandry Tracker" for the app and
  "CaskAbove" for the publisher; "HerpTracker" / "Herp Tracker" may only appear as history (for
  example, "originally a personal tracker I called Herp Tracker").
- Tracked in Jira as RHA-10 (naming decision) and RHA-52 (rename across UI, docs and repo).
