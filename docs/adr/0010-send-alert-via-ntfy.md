# Send Alert notifies via ntfy, with a debounced per-condition state machine

**Status**: accepted

Nothing in HerpMonitor today reaches the user proactively — Target Range breaches only recolor a
dashboard pill, which only helps if someone happens to be looking. A heat/humidity failure
overnight (a burnt-out UTH, a dead heat bulb) is animal-welfare-critical and needs to reach the
user away from the dashboard, not wait until morning's page load. Considered SMTP email and
Pushover as delivery channels; picked **ntfy** for being the simplest to stand up — a plain HTTP
POST to a topic, no account provisioning beyond picking a topic name, with self-hosting available
later if wanted. This is the first external network dependency this app has ever had.

Three Alert Conditions exist: **Out of Target Range** (Sensor), **Zero Power While On** (Plug, see
ADR 0009), and **Unreachable** (Sensor or Plug — no successful Reading/Data Capture collected in at
least the debounce window). Each is tracked per entity+condition as a state machine — `normal` →
`pending` → `alerting` → `resolved` — rather than a stateless per-poll check, so a single noisy
reading or momentary network blip doesn't fire a false alarm: a condition must stay continuously
abnormal for the **Alert Debounce** duration (an `app_setting` value, default 10 minutes, same
pattern as Refresh Timeout) before it actually fires. It fires exactly once on entering `alerting`
(no repeat notifications while the underlying problem persists) and once more on returning to
`resolved`, so the user always learns both when something broke and when it got fixed.

**Consequences**: new state-tracking table (entity type+id, condition kind, current state,
state-entered timestamp) evaluated on a timer; `app_setting` gains an `alert_debounce_minutes`
column plus ntfy configuration (topic, server URL). Evaluation needs to run somewhere periodic —
most likely folded into the existing `tuya_collector.py`/`govee_collector.py` loops per condition's
entity type, rather than standing up a fourth service, to keep ADR 0001's three-service shape.
Exact evaluator placement is an implementation detail for later.
