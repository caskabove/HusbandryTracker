# Schedule splits into Target Schedule + Detected Schedule, with a drift-based Timer Warning

**Status**: accepted

Until now, a Plug's Schedule was one value, shape determined entirely by Tracking Mode: a Smart
Plug showed an Inferred Schedule (never actually implemented — `inferred_schedule` was a permanent
`None` stub), a Manual Plug showed a Declared Schedule (`declared_on_time`/`declared_off_time`,
entered directly, unverified). The two were mutually exclusive by construction — a Smart Plug had
nowhere to enter an expected on/off time at all.

Real husbandry use wants both at once for a monitored Plug: what you *set the timer to* and what's
*actually happening*, side by side, so a drifting mechanical timer or a misconfigured smart
schedule shows up instead of silently drifting. Renamed/reshaped accordingly (see CONTEXT.md:
Schedule, Target Schedule, Detected Schedule, Timer Warning):

- **Target Schedule** (`plug.target_on_time`/`target_off_time`, renamed from
  `declared_on_time`/`declared_off_time`) — the on/off time you expect, entered directly. No longer
  Manual-only: available on any Plug without a Controller Kind, Smart or Manual alike.
- **Detected Schedule** — actually built now. Computed on demand from `plug_state_transition`
  (the time-of-day of the most recent transition to on, and separately to off), not stored as a
  column. Deliberately the *latest observed instance* of each, not a multi-day average — simpler to
  compute and to explain, and reasonable to revisit if it proves too noisy day-to-day in practice.
- **Timer Warning** — when both exist for a Smart Plug and disagree by more than
  `app_setting.schedule_drift_threshold_minutes` (default 15) on either time independently, that
  time renders in red. Comparison is wraparound-aware (23:50 vs 00:05 is 15 minutes apart, not 23
  hours). Purely visual for now — not wired into Send Alert/ntfy (ADR 0010); doing so later is a
  small, natural extension (a fourth Alert Condition) once the visual version has been lived with.

A Manual Plug shows its Target Schedule alone, exactly as Declared Schedule worked before — nothing
to detect, nothing to warn about, no behavior change there.

**Consequences**: live-db migration renames `plug.declared_on_time`/`declared_off_time` to
`target_on_time`/`target_off_time` (`tools/migrate_2026_08_25_target_schedule.py`) and adds
`app_setting.schedule_drift_threshold_minutes`. `_validate_plug`'s both-or-neither check on the two
time fields now applies whenever `controller_kind == 'none'`, regardless of Tracking Mode, not only
for Manual. Detected Schedule is computed per-request (a couple of indexed lookups against
`plug_state_transition`) rather than cached — acceptable at this app's write volume and page-view
frequency; revisit if the Plugs list ever needs to scale far beyond a personal collection.
