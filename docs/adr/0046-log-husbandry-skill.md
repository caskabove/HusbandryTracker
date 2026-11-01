# `/log-husbandry` resolves names itself from a Registry export; Ingest applies and re-validates

**Status**: accepted

**Context**: `/log-husbandry` is a Skill (see ADR 0045; CONTEXT.md: Skill) that turns a sentence
like "fed Bob a large mouse and cleaned his water" into real Care Events. The Skill explicitly must
not have direct database access — it needs to keep working even when Husbandry Tracker's own
processes aren't running at all, the same resilience guarantee a device Plugin already gets from
the Inbox/Registry contract (ADR 0013). That rules out calling `web/admin_queries.py`'s
`log_feeding()`/`log_care_event()` directly, the same way a device Plugin never imports `db.db`.

**Decision**: Ingest exports a Registry for `log_husbandry` the same way it does for any other
Plugin (`data/registry/log_husbandry.json`), shaped around what this Skill actually needs instead
of a device list — flat `rooms`/`enclosures`/`animals` arrays, each with its id and name (and each
Enclosure/Animal's parent id). The Skill matches names against this snapshot itself
(case-insensitive exact match for v1 — no fuzzy/nickname matching), asking the user to disambiguate
in-conversation on a no-match or multi-match, and resolves pronouns like "his water" to the right
Enclosure (Watering/Cleaning are always Enclosure-scoped, never Animal-scoped — see CONTEXT.md:
Watering / Cleaning). Only once the user confirms a combined summary of everything a whole
utterance parsed into (one confirmation for the batch, not one per event) does the Skill write —
one Inbox file per event, matching every other kind's one-file-per-observation granularity, at
`data/inbox/care_event/`, using a new Plugin Event kind (see CONTEXT.md: Care Event Plugin Event)
whose payload already carries resolved ids (`enclosure_id`, `animal_id?`, `care_kind`, plus
Feeding Detail fields when relevant) rather than raw names — Ingest's job at drain time is the
cheap, authoritative part: re-validate those ids still exist and still relate the way the event
claims, since the Registry snapshot the Skill read from could be stale by the time the file is
actually processed.

Three things that need a human and can't be done from the Registry snapshot alone are deliberately
left to Ingest instead of the Skill: (1) **omitted Feeding Detail fields** — when the sentence
doesn't say what was fed, the Skill leaves `food`/`count`/`prey_state`/`result` out of the payload
entirely, and Ingest fills them in via the existing `get_last_feeding_detail()` lookup (the same
"repeat last Feeding" rule the Log Feeding Dialog's quick-log buttons already use — ADR 0042),
falling back to `frozen_thawed`/`accepted` only when there's truly no prior Feeding; (2) **a stale
resolution at drain time** quarantines the event (into `_rejected`, same mechanism schema
violations already use) rather than silently dropping it the way a routine device poll's
unresolved event does — this is a one-off, human-confirmed action, not a noisy recurring signal,
so a failure needs to stay visible; (3) **a date reference in the sentence** ("fed Bob yesterday")
is detected and surfaces as "I can only log this as happening now — backdating isn't supported
yet," never silently logged against the wrong/a guessed timestamp. Vocabulary mapping (a sentence
saying "frozen" or "wouldn't eat" rather than the stored `frozen_thawed`/`refused` enum values) is
the Skill's own job, done before anything is written — Ingest only ever receives already-valid
enum values for this kind.

**Considered Options**:
- **The Skill calls `log_feeding()`/`log_care_event()` directly** — rejected: breaks the
  resilience guarantee that's the entire point of modeling this as a Plugin at all; the app not
  running at the moment someone talks to the Skill would mean the action is just lost.
  (Earlier in this design, this is in fact where the first instinct landed, and was walked back for
  exactly this reason.)
- **The Registry snapshot also carries feeding history** so the Skill can compute the "last
  Feeding" fallback itself — rejected: keeps that business rule in exactly one place
  (`web/admin.py`'s quick-log route gains a second caller instead of the rule being duplicated),
  and avoids bloating the snapshot with history the Skill otherwise never needs.
- **Silently dropping a stale/unresolved `care_event`**, matching every other kind — rejected:
  acceptable for a routine device poll that just retries next cycle, wrong for a specific action a
  human just confirmed, where "nothing happened and no one knows" is a real foot-gun.
- **Fuzzy/nickname name matching** for v1 — rejected as unnecessary scope for how small this app's
  Room/Enclosure/Animal counts actually are; left open for later if it turns out to matter.

**Consequences**: `schemas/plugin_event.schema.json` gains `care_event` as a `kind`;
`ingest/ingest.py` gains a resolve-and-apply branch for it, including the `get_last_feeding_detail()`
fallback call; `plugins/log_husbandry/` is the first Plugin built against the Plugin Contract (ADR
0045). Shed Log, Animal Log, and Plant Health are explicitly **not** covered by this Skill yet —
only the four Care Event kinds (Feeding, Watering, Spot-clean, Deep-clean) — left as a natural
follow-on once this first kind is proven out.
