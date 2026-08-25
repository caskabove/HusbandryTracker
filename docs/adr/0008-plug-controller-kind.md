# Plug gains a three-way Controller Kind, replacing the Thermostat-Controlled boolean

**Status**: accepted

**Supersedes ADR 0007.** ADR 0007 added `is_thermostat_controlled` (boolean) + `target_temp_c` to
`plug`. Extending Plug monitoring to humidity-controlled setups (a MistKing misting system's
control unit, a humidistat-driven fogger — Hydrostat-Controlled) as a second independent boolean
would allow an invalid combined state (both true at once), even though a Plug is physically one
relay powering one downstream device — it's never both a thermostat and a humidistat at the same
time.

Replaced with a single `controller_kind` field: `none` (the Plug powers the heat/cooling/moisture
source directly — the common case) | `thermostat` | `hydrostat`, mutually exclusive by
construction rather than by a cross-column CHECK. `thermostat` pairs with `target_temp_c` (unchanged
from ADR 0007); `hydrostat` pairs with a new `target_humidity_pct`. Either kind suppresses Schedule
display entirely (Inferred or Declared), same reasoning as ADR 0007: the actual on/off cycling
happens downstream of the Plug, invisible to Tuya and to observation.

**Consequences**: `plug.is_thermostat_controlled` is replaced by `plug.controller_kind TEXT NOT
NULL DEFAULT 'none' CHECK (controller_kind IN ('none', 'thermostat', 'hydrostat'))`; `plug` gains
`target_humidity_pct` (nullable) alongside the existing `target_temp_c`. Required-together validation
(a controller kind needs its matching setpoint, and clears a Manual Plug's Declared Schedule fields)
stays in `web/admin_queries.py`, same pattern as before. The in-flight, uncommitted checkbox UI for
`is_thermostat_controlled` (`web/admin.py`, `web/static/app.js`, `web/static/style.css`,
`web/templates/admin_plug_edit.html`) predates this ADR and needs reworking into a `controller_kind`
select before it lands — never committed, so no migration cost, just unfinished work to redo.
