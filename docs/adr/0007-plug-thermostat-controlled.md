# Plug gains a Thermostat-Controlled flag, replacing Schedule with a Target Temperature

**Status**: superseded by ADR 0008

A common real wiring for a heat source is Plug → separate thermostat unit (Herpstat, Vivarium
Electronics, Jump Start, etc.) → heat lamp/UTH, not Plug → heat source directly. In that setup the
Plug's own relay is just a master power switch for the thermostat and stays on continuously — the
actual on/off cycling happens downstream of the Plug, invisible to Tuya. Today's Schedule (Inferred
from observed transitions, or Declared for a Manual Plug) would show "always on" or require a fake
Declared time, either way misrepresenting what's actually happening to the animal's heat.

A Plug gains an independent **Thermostat-Controlled** flag (see `CONTEXT.md`), orthogonal to
Tracking Mode — a Smart or a Manual Plug can each be marked Thermostat-Controlled, since the
thermostat's cycling is invisible either way. When set, the Plug shows no Schedule at all (Inferred
or Declared) and instead shows a **Target Temperature**: a single setpoint value, entered directly
(there's no device to read a physical thermostat's dial from), matching how you'd actually transcribe
it off the unit. Rejected a min/max range shape (mirroring Sensor's Target Range) — a thermostat
dial gives you one number, not a tolerance band you'd usually know; a real Target Range still exists
on a Sensor if you want the room/enclosure judged against an actual acceptable range.

**Consequences**: `plug` gains `is_thermostat_controlled` (boolean, default 0) and `target_temp_c`
(nullable). Required together at save time (a friendly error, not a CHECK — same pattern as Manual
Sensor's Target Range requirement): Thermostat-Controlled needs a Target Temperature, and a Manual
Plug's Declared Schedule fields are cleared when Thermostat-Controlled is set, since they'd otherwise
sit around unused and out of sync with what's actually shown. A Smart + Thermostat-Controlled Plug
still gets polled and its transitions still get recorded (harmless, low-cost) — only the *display* of
an Inferred Schedule is suppressed, not the underlying collection.
