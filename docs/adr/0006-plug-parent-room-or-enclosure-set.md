# Plug's parent generalized to a Room or a set of Enclosures

**Status**: accepted

A Plug's parent was a single required `enclosure_id` — one Plug, one Enclosure, no exceptions.
That stopped matching two real setups: a genuinely room-wide fixture (a rack's ambient light, not
tied to any one tub), and smaller collections where "everything is on one switch" — a single
physical Plug wired to several specific tubs at once, not necessarily grouped into a Room at all.

Mirroring Sensor's existing Room-or-Enclosure split (ADR 0004), a Plug now belongs to either **one
Room**, or **one-or-more Enclosures** — never both, never neither. The Enclosure side needed a real
relational change, not just a nullable column: `plug.enclosure_id` is replaced by a `plug_enclosure`
join table (one row per Plug↔Enclosure pairing), used uniformly even for the common single-Enclosure
case, rather than keeping the old scalar column for that case and bolting a join table on only for
the multi-Enclosure one. A hybrid would mean every "which Enclosure(s) does this Plug belong to"
read has to check two places and reconcile them; one join table, one path, matches how Sensor's
parent was already kept to a single clean rule instead of special-casing the common case.

Purpose, Tracking Mode, and Schedule all stay single values on the Plug itself, applying identically
to whichever Enclosure(s) it serves — it's one physical device doing one physical job, regardless of
how many tubs share it. The parent-set invariant (Room XOR ≥1 Enclosure) is cross-table, so it's
validated in `web/admin_queries.py` with a friendly error, the same pattern already used for Manual
Sensor's Target Range requirement — SQLite CHECK constraints can't see another table's rows.

Deleting a Plug's *last* remaining parent is handled two different ways, matching whichever existing
precedent already covers that kind of loss:
- **A Room-owned Plug's Room is deleted** → the Plug is deleted too, same as a Room's Sensors already
  cascade-delete with it (`ON DELETE CASCADE`).
- **An Enclosure-linked Plug loses its last Enclosure** (that Enclosure is deleted) → the Plug moves
  to **Unassigned** (see `CONTEXT.md`) instead, the same holding pen already used for a newly-found
  Smart Plug with nowhere to go yet. Rejected the alternative of deleting it here too: a Plug's Tuya
  credentials took real one-time setup effort to obtain (see the User Guide's Smart Life note) — losing
  them because the *last* Enclosure happened to get deleted is a worse outcome than a Sensor losing a
  Room-scoped ambient value that costs nothing to re-add.

**Consequences**: `plug.enclosure_id` is gone; `plug.room_id` (nullable, `ON DELETE CASCADE`) is
added alongside the new `plug_enclosure` join table. `delete_enclosure` now has to check, before
deleting, whether any linked Plug would be left with zero Enclosures and re-link those specific
Plugs to Unassigned first — plain `ON DELETE CASCADE` on the join table alone can't do that
(it only removes the one link, it can't also insert a replacement one), so this step happens in
`web/admin_queries.py`, not the schema. Admin gains a way to pick multiple Enclosures for one Plug
instead of exactly one.
