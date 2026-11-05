# A Timer-Controlled Plug's Target Schedule gains up to 3 on/off cycles

**Status**: accepted

**Extends ADR 0041.** Target Schedule has always meant exactly one on-time/off-time pair. Real
timers often run more than once a day — a basking light on in the morning and again in the evening,
a misting pump cycling three times — which the single pair couldn't represent at all; the only
workaround was a second, separate Plug for the same physical outlet, which fit neither the data
model nor reality. The user asked for a Timer-Controlled Plug (Smart or Manual alike) to carry
multiple on/off cycles directly.

Settled on **3 cycles, fixed**, rather than an open-ended list: covers every real case described
(2-3 cycles/day) without the added schema (a child table) and UI (dynamic add/remove rows) an
arbitrary-length list would need. Cycle 1 keeps `plug.target_on_time`/`target_off_time`'s existing
columns/behavior unchanged; Cycles 2 and 3 are new, optional, nullable `target_on_time_2`/
`target_off_time_2` and `target_on_time_3`/`target_off_time_3` columns, each still its own
both-or-neither pair, and contiguous (Cycle 2 needs Cycle 1 set, Cycle 3 needs Cycle 2) so a Plug's
configured cycles are never gapped.

**Detected Schedule stays exactly as it was** — still just the single most-recently-observed
on-transition and off-transition, not cycle-aware. Making it cycle-aware (scanning
`plug_state_transition` history to work out which detected transition belongs to which configured
cycle) was considered and rejected as a much bigger change for a questionable payoff: a Plug's
real-world on/off pattern can drift, skip a cycle, or run unplugged for a while, and reliably
attributing each transition to "the" cycle it was supposed to be isn't something the data actually
supports. Instead, **Timer Warning compares each detected time against whichever configured cycle's
time is nearest to it** (`web/status.py`'s new `nearest_target_time()`), wraparound-aware same as
the drift check itself. This keeps the comparison meaningful with multiple cycles configured without
pretending to know which cycle fired.

**Consequences**:
- `db/schema.sql`'s `plug` table gains the 4 new columns (plain nullable `TEXT`, no new CHECK — see
  `tools/migrate_2026_11_04_plug_timer_multi_cycle.py` for the live-DB migration) and `schemas/plug.py`'s
  `PlugBase` mirrors them.
- `web/admin_queries.py`'s `_validate_plug()` gains the per-cycle both-or-neither and contiguity
  rules; `create_plug()`/`update_plug()` clear all 3 cycles together when Controller Kind isn't
  `timer`, same as Cycle 1 always did alone. `update_plug()`'s Timer Warning re-arm check now
  compares all 3 cycles, not just Cycle 1 — changing any cycle re-arms a cleared warning.
  `timer_ack_on_time`/`timer_ack_off_time` stay a single pair — Detected Schedule itself is still
  single-valued, so one ack pair per side is still enough.
- The duplicated Detected-Schedule-attaching block across `get_enclosure()`/`get_plug()`/
  `list_plugs()`/`get_room()` was factored into one `_attach_schedule()` helper, extended to also
  compute `matched_target_on_time`/`matched_target_off_time` (via `nearest_target_time()`) and
  `has_target_schedule` (true if any cycle is configured) — every template reads these instead of
  Cycle 1's raw columns directly for its drift-colored pill/condition.
- Every Plug add/edit form (`admin_plug_edit.html`, `admin_index.html`'s Add Plug, `setup_plug.html`,
  `add_pet_plug.html`) grew 2 more on/off time rows, each still validated client-side by the existing
  `validateBothOrNeitherOnSubmit()` (called once per cycle). `web/setup.py`'s simpler
  `setup_create_room_plug` (no Controller Kind picker at all, by design) stays single-cycle — more
  cycles can be added afterward from the Plug's own Admin Edit page.
- Every read-only Schedule display (`admin_room.html`, `admin_index.html`, `admin_enclosure.html`,
  `dashboard.html`) shows every configured cycle via a new shared macro,
  `_plug_cycles_macro.html`'s `cycles_text()`, rather than just Cycle 1.
