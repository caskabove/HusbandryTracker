-- HerpMonitor schema.
-- Terminology matches CONTEXT.md — read that first if a name here is surprising.

PRAGMA foreign_keys = ON;

-- App-wide settings — a single row, not a generic key-value store, since there's only a handful of
-- settings (see CONTEXT.md: Refresh, Alert Debounce; ADR 0005, ADR 0010). Add columns here as more
-- settings arise; don't generalize to a key-value shape ahead of actually needing it.
CREATE TABLE IF NOT EXISTS app_setting (
    id                             INTEGER PRIMARY KEY CHECK (id = 1),
    ble_refresh_timeout_seconds    INTEGER NOT NULL DEFAULT 30,
    alert_debounce_minutes         INTEGER NOT NULL DEFAULT 10,  -- see CONTEXT.md: Alert Debounce, ADR 0010
    ntfy_server_url                TEXT,                         -- e.g. "https://ntfy.sh"; NULL/empty disables Send Alert delivery
    ntfy_topic                     TEXT,
    schedule_drift_threshold_minutes INTEGER NOT NULL DEFAULT 15, -- see CONTEXT.md: Timer Warning, ADR 0012
    ingest_scan_interval_seconds   INTEGER NOT NULL DEFAULT 5    -- see CONTEXT.md: Ingest; ADR 0013
);
INSERT OR IGNORE INTO app_setting (id) VALUES (1);

-- A named grouping of Enclosures sharing a physical space. See CONTEXT.md: Room, Light Schedule.
-- No Animals, Bioactive flag, or Care Events here — a Room isn't a housing unit, it's a grouping +
-- ambient-monitoring layer around one or more Enclosures.
CREATE TABLE IF NOT EXISTS room (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    light_on_time   TEXT,    -- "HH:MM", Light Schedule — both-or-neither with light_off_time
    light_off_time  TEXT,    -- "HH:MM"
    light_notes     TEXT,    -- free text, independent of whether a time is set
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- enclosure_type gates which Target Range columns on `sensor` are relevant/shown for this
-- Enclosure's Sensors — see CONTEXT.md: Enclosure Type, ADR 0011. Which columns apply to which
-- type lives in code (schemas/enclosure_types.py), not here.
CREATE TABLE IF NOT EXISTS enclosure (
    id                        INTEGER PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
    room_id                   INTEGER REFERENCES room(id) ON DELETE SET NULL,  -- optional (see CONTEXT.md: Room)
    fallback_sensor_id        INTEGER REFERENCES sensor(id) ON DELETE SET NULL,  -- see CONTEXT.md: Fallback Sensor
    enclosure_type            TEXT NOT NULL DEFAULT 'basic'
                                   CHECK (enclosure_type IN ('basic', 'freshwater', 'saltwater', 'amphibian')),
    bioactive                 INTEGER NOT NULL DEFAULT 0,   -- 0/1, independent of enclosure_type (see CONTEXT.md: Bioactive)
    feeding_interval_days     INTEGER NOT NULL DEFAULT 7,
    watering_interval_days    INTEGER NOT NULL DEFAULT 3,
    spot_clean_interval_days  INTEGER NOT NULL DEFAULT 7,
    deep_clean_interval_days  INTEGER NOT NULL DEFAULT 30,
    created_at                TEXT NOT NULL DEFAULT (datetime('now'))
);

-- An individual live plant tracked within a Bioactive Enclosure (see CONTEXT.md: Plant). Creation
-- is only meaningful when the parent Enclosure is Bioactive — enforced in web/admin_queries.py,
-- not here, same pattern as the other cross-row invariants in this file.
CREATE TABLE IF NOT EXISTS plant (
    id           INTEGER PRIMARY KEY,
    enclosure_id INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    species      TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A manually-logged, backdatable Plant Health observation (see CONTEXT.md: Plant Health) — scoped
-- to the Enclosure as a whole (plant_id NULL) or one specific Plant. Deliberately not a care_event
-- kind: it's a status observation, not an action performed, and keeping it separate avoids stacking
-- a second conditionally-valid entity reference onto care_event alongside Spot-feed's animal_id.
CREATE TABLE IF NOT EXISTS plant_health_log (
    id           INTEGER PRIMARY KEY,
    enclosure_id INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    plant_id     INTEGER REFERENCES plant(id) ON DELETE CASCADE,  -- nullable: enclosure-wide vs one Plant
    note         TEXT NOT NULL,
    occurred_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_plant_health_log_enclosure_time ON plant_health_log (enclosure_id, occurred_at);

CREATE TABLE IF NOT EXISTS animal (
    id                  INTEGER PRIMARY KEY,
    enclosure_id        INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    species_common      TEXT,
    species_scientific  TEXT,
    dob                 TEXT,  -- ISO date, nullable (not always known)
    -- Whether this Animal's card shows on the Dashboard's Enclosure panel — an Enclosure housing a
    -- colony can have more Animals than fit comfortably at a glance, so this is opt-in per Animal,
    -- toggled from the Enclosure's own Admin page. Defaults on; web/admin_queries.py's
    -- create_animal() only auto-enables it for the first 3 Animals in an Enclosure (see
    -- CONTEXT.md: Animal) — after that, a new Animal defaults off until the user picks it.
    show_on_dashboard   INTEGER NOT NULL DEFAULT 1
);

-- A Sensor assigned to either an Enclosure or a Room, never both. See CONTEXT.md: Sensor,
-- Tracking Mode, Target Range, Room, Plugin, External ID, Plugin Config; ADR 0013.
--
-- tracking_mode = 'smart': a real device, polled/listened-to by its owning Plugin — plugin and
-- external_id required (e.g. plugin='govee_ble', external_id=the MAC address). tracking_mode =
-- 'manual': no physical device — plugin/external_id/plugin_config stay NULL, and Readings are
-- hand-logged through the Admin UI instead. A Manual Sensor must have a complete Target Range
-- (min AND max) on at least one metric before it's useful, but which metric is up to the user (an
-- IR thermometer spot-check has no humidity number to give) — that "at least one" rule is enforced
-- in web/admin_queries.py with a friendly error, not here, so a bad value gets a clear message
-- instead of a raw SQLite CHECK failure.
-- target_ph/ammonia/nitrite/nitrate are Freshwater+ (see CONTEXT.md: Enclosure Type);
-- target_specific_gravity/salinity/alkalinity/calcium/magnesium/phosphate are Saltwater-only.
-- Specific Gravity and Salinity are two separate Target Range metrics (e.g. 1.026 SG / 35 ppm) —
-- both describe the same water property, read off different instruments, so they're tracked and
-- targeted independently rather than one derived from the other. Which columns are
-- shown/editable for a given Sensor depends on its Enclosure's enclosure_type, decided in code
-- (schemas/enclosure_types.py) — see ADR 0011. Ammonia/nitrite/phosphate "min" will usually just be
-- 0 (the target is "as low as possible"), stored as a real min/max pair anyway for the same shape
-- as every other Target Range metric.
CREATE TABLE IF NOT EXISTS sensor (
    id                    INTEGER PRIMARY KEY,
    enclosure_id          INTEGER REFERENCES enclosure(id) ON DELETE CASCADE,
    room_id               INTEGER REFERENCES room(id) ON DELETE CASCADE,
    label                 TEXT NOT NULL,             -- e.g. "warm side", "cool side"
    tracking_mode         TEXT NOT NULL DEFAULT 'smart' CHECK (tracking_mode IN ('smart', 'manual')),
    plugin                TEXT,                      -- e.g. "govee_ble"; NULL for Manual — see CONTEXT.md: Plugin
    external_id           TEXT,                      -- opaque per-Plugin device id, e.g. a MAC address — see CONTEXT.md: External ID
    plugin_config         TEXT,                      -- opaque JSON credentials, NULL if the Plugin needs none — see CONTEXT.md: Plugin Config
    auto_update_enabled   INTEGER NOT NULL DEFAULT 1, -- 0/1, Smart Sensor only (see CONTEXT.md: Auto-Update)
    -- Whether this Sensor's Reading row shows on the Dashboard (Enclosure panel or Room ambient
    -- strip) — an Enclosure or Room can end up with more Sensors than fit at a glance (e.g. several
    -- water-chemistry probes). Opt-in per Sensor, toggled from its parent's Admin page. Defaults on;
    -- web/admin_queries.py's create_sensor()/create_room_sensor() only auto-enable it for the first
    -- 3 Sensors under the same parent — same "top 3" default as animal.show_on_dashboard.
    show_on_dashboard     INTEGER NOT NULL DEFAULT 1,
    target_temp_min_c     REAL,
    target_temp_max_c     REAL,
    target_humidity_min   REAL,
    target_humidity_max   REAL,
    target_ph_min         REAL,
    target_ph_max         REAL,
    target_ammonia_ppm_min      REAL,
    target_ammonia_ppm_max      REAL,
    target_nitrite_ppm_min      REAL,
    target_nitrite_ppm_max      REAL,
    target_nitrate_ppm_min      REAL,
    target_nitrate_ppm_max      REAL,
    target_specific_gravity_min REAL,
    target_specific_gravity_max REAL,
    target_salinity_ppm_min     REAL,
    target_salinity_ppm_max     REAL,
    target_alkalinity_dkh_min   REAL,
    target_alkalinity_dkh_max   REAL,
    target_calcium_ppm_min      REAL,
    target_calcium_ppm_max      REAL,
    target_magnesium_ppm_min    REAL,
    target_magnesium_ppm_max    REAL,
    target_phosphate_ppm_min    REAL,
    target_phosphate_ppm_max    REAL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (plugin, external_id),
    CHECK (
        (tracking_mode = 'smart' AND plugin IS NOT NULL AND external_id IS NOT NULL) OR
        (tracking_mode = 'manual' AND plugin IS NULL AND external_id IS NULL)
    ),
    CHECK (
        (enclosure_id IS NOT NULL AND room_id IS NULL) OR
        (enclosure_id IS NULL AND room_id IS NOT NULL)
    )
);

-- Per-Sensor Alert state machine (see CONTEXT.md: Alert, Alert Condition, ADR 0010) — normal /
-- pending / alerting / resolved, tracked per (sensor, condition) so debounce timing and "fire once"
-- behavior survive across polls. A real FK table per entity kind (this one, and plug_alert_state
-- below) rather than one polymorphic entity_type+entity_id table, matching how this schema always
-- prefers explicit typed references over a generic shape.
CREATE TABLE IF NOT EXISTS sensor_alert_state (
    id               INTEGER PRIMARY KEY,
    sensor_id        INTEGER NOT NULL REFERENCES sensor(id) ON DELETE CASCADE,
    condition_kind   TEXT NOT NULL CHECK (condition_kind IN ('out_of_range', 'unreachable')),
    state            TEXT NOT NULL DEFAULT 'normal' CHECK (state IN ('normal', 'pending', 'alerting', 'resolved')),
    state_entered_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (sensor_id, condition_kind)
);

-- A Plug, belonging to either one Room or one-or-more Enclosures (via plug_enclosure below), never
-- both. See CONTEXT.md: Plug, Purpose, Tracking Mode, Schedule, Unassigned. See ADR 0006 for why
-- the Enclosure side is a join table even for the common single-Enclosure case, and why an
-- Enclosure-linked Plug moves to Unassigned (not deleted) if it loses its last Enclosure, while a
-- Room-owned Plug is deleted along with its Room (matching how a Room's Sensors already cascade).
--
-- tracking_mode = 'smart': a real device, polled by its owning Plugin — plugin and external_id
-- required (e.g. plugin='tuya_lan', external_id="<tuya device_id>:<switch_dps_key>", plugin_config
-- carrying the Tuya local_key/ip_address — see CONTEXT.md: Plugin, External ID, Plugin Config; ADR
-- 0013). tracking_mode = 'manual': no device, e.g. a mechanical timer — plugin/external_id/
-- plugin_config all stay NULL.
--
-- target_on_time/target_off_time hold the Target Schedule (see CONTEXT.md: Target Schedule, ADR
-- 0012) — available on any Plug without a Controller Kind, Smart or Manual alike. For a Manual
-- Plug it's the only schedule info there is (nothing to observe). For a Smart Plug it's compared
-- against the Detected Schedule (computed from plug_state_transition, not stored), flagged as a
-- Timer Warning when they drift apart by more than schedule_drift_threshold_minutes
-- (app_setting). Superseded "Declared Schedule" from earlier versions of this app, which only ever
-- existed for a Manual Plug with no comparison possible.
--
-- Not every physical Tuya device is a single-outlet plug: multi-outlet power strips expose several
-- independently-switched DPS keys (e.g. "1"/"2"/"3" for three AC outlets, "7" for a USB port) on
-- ONE device_id. Each outlet is its own Plug row here, sharing the same plugin_config (local_key/
-- ip) but a different switch_dps_key baked into its own external_id — hence the unique constraint
-- being on (plugin, external_id), not on external_id's device_id portion alone (see
-- plugins/tuya_lan/identity.py for the encode/decode). Manual Plugs all have external_id NULL,
-- which SQLite treats as distinct per row in a UNIQUE index, so multiple Manual Plugs never
-- collide on that constraint.
--
-- The Room-XOR-Enclosure-set invariant can't be a single-table CHECK (it depends on plug_enclosure
-- row counts) — enforced in web/admin_queries.py instead, same pattern as Manual Sensor's Target
-- Range requirement.
CREATE TABLE IF NOT EXISTS plug (
    id                  INTEGER PRIMARY KEY,
    room_id             INTEGER REFERENCES room(id) ON DELETE CASCADE,
    label               TEXT NOT NULL,                  -- e.g. "basking bulb", "UTH"
    purpose             TEXT NOT NULL CHECK (length(purpose) > 0),  -- free text; Admin suggests common values, doesn't restrict to them
    tracking_mode       TEXT NOT NULL DEFAULT 'smart' CHECK (tracking_mode IN ('smart', 'manual')),
    plugin              TEXT,                           -- e.g. "tuya_lan"; NULL for Manual — see CONTEXT.md: Plugin
    external_id         TEXT,                           -- opaque per-Plugin device id — see CONTEXT.md: External ID
    plugin_config       TEXT,                           -- opaque JSON credentials (Tuya local_key/ip_address) — see CONTEXT.md: Plugin Config
    auto_update_enabled INTEGER NOT NULL DEFAULT 1,     -- 0/1, Smart Plug only (see CONTEXT.md: Auto-Update)
    -- Whether this Plug's current status (on/off, or Unreachable) shows on the Dashboard — a Room
    -- or Enclosure can end up with more Plugs than fit at a glance. Opt-in per Plug, toggled from
    -- its parent's Admin page. Defaults on; web/admin_queries.py's create_plug() only auto-enables
    -- it for the first 3 Plugs under the same parent — same "top 3" default as animal/sensor's own
    -- show_on_dashboard.
    show_on_dashboard   INTEGER NOT NULL DEFAULT 1,
    target_on_time      TEXT,                           -- "HH:MM", never with a Controller Kind set (see CONTEXT.md: Target Schedule)
    target_off_time     TEXT,                           -- "HH:MM", never with a Controller Kind set
    -- Always On (see CONTEXT.md: Plug) — e.g. a pump that runs continuously. Only meaningful when
    -- controller_kind = 'none' and mutually exclusive with target_on_time/target_off_time, same
    -- split as this table's other cross-column Plug rules: enforced in web/admin_queries.py, not
    -- a CHECK here.
    always_on           INTEGER NOT NULL DEFAULT 0,
    controller_kind     TEXT NOT NULL DEFAULT 'none' CHECK (controller_kind IN ('none', 'thermostat', 'hydrostat')),  -- see CONTEXT.md: Controller Kind, ADR 0008 (supersedes ADR 0007's is_thermostat_controlled)
    target_temp_c       REAL,                           -- required together with controller_kind = 'thermostat'; enforced in web/admin_queries.py, not here
    target_humidity_pct REAL,                           -- required together with controller_kind = 'hydrostat'; enforced in web/admin_queries.py, not here
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (plugin, external_id),
    CHECK (
        (tracking_mode = 'smart' AND plugin IS NOT NULL AND external_id IS NOT NULL) OR
        (tracking_mode = 'manual' AND plugin IS NULL AND external_id IS NULL)
    )
);

-- Last time ANY plug_state Plugin Event arrived for a Smart Plug, updated on every poll regardless
-- of whether the on/off state changed — drives Plug Unreachable (see CONTEXT.md: Unreachable,
-- Ingest; ADR 0013) without polluting plug_state_transition's edge-triggered semantics, which
-- Detected Schedule depends on staying pure (only real transitions, never every poll).
CREATE TABLE IF NOT EXISTS plug_last_seen (
    plug_id      INTEGER PRIMARY KEY REFERENCES plug(id) ON DELETE CASCADE,
    last_seen_at TEXT NOT NULL
);

-- Which Enclosure(s) a non-Room-owned Plug belongs to — see the plug table's comment and ADR 0006.
-- Almost always exactly one row per Plug; more than one means a single physical switch wired to
-- several tubs at once ("everything on one switch" — common in smaller collections).
CREATE TABLE IF NOT EXISTS plug_enclosure (
    plug_id      INTEGER NOT NULL REFERENCES plug(id) ON DELETE CASCADE,
    enclosure_id INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    PRIMARY KEY (plug_id, enclosure_id)
);

-- Raw Sensor readings, captured continuously (see CONTEXT.md decision: capture everything, no charts in v1).
-- temperature_c/humidity_pct/battery_pct are the only columns a Smart Sensor (Govee BLE) ever
-- writes to. The water-chemistry columns below exist for Manual Sensors tracking a non-basic
-- Enclosure Type's Target Range metrics (see CONTEXT.md: Enclosure Type, Reading; ADR 0011) —
-- hand-logged through the Admin UI/Dashboard, one value per metric that Sensor actually tracks,
-- same "at least one populated column" shape sensor_reading already had for temp/humidity. Column
-- names mirror `sensor`'s own target_<metric>_min/max naming (minus "target_"/"_min"/"_max") — see
-- schemas/enclosure_types.py's TARGET_RANGE_METRICS.reading_column, the single source of truth
-- mapping a metric to both its Target Range columns here and its Reading column there.
CREATE TABLE IF NOT EXISTS sensor_reading (
    id             INTEGER PRIMARY KEY,
    sensor_id      INTEGER NOT NULL REFERENCES sensor(id) ON DELETE CASCADE,
    recorded_at    TEXT NOT NULL DEFAULT (datetime('now')),
    temperature_c  REAL,
    humidity_pct   REAL,
    battery_pct    INTEGER,
    ph             REAL,
    ammonia_ppm    REAL,
    nitrite_ppm    REAL,
    nitrate_ppm    REAL,
    specific_gravity REAL,
    salinity_ppm   REAL,
    alkalinity_dkh REAL,
    calcium_ppm    REAL,
    magnesium_ppm  REAL,
    phosphate_ppm  REAL
);
CREATE INDEX IF NOT EXISTS idx_sensor_reading_sensor_time ON sensor_reading (sensor_id, recorded_at);

-- Edge-triggered Plug relay-state changes only (not a poll log) — this is what Schedule is derived from.
CREATE TABLE IF NOT EXISTS plug_state_transition (
    id          INTEGER PRIMARY KEY,
    plug_id     INTEGER NOT NULL REFERENCES plug(id) ON DELETE CASCADE,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_on       INTEGER NOT NULL   -- 0/1
);
CREATE INDEX IF NOT EXISTS idx_plug_transition_plug_time ON plug_state_transition (plug_id, recorded_at);

-- One row per Command sent to a Plug — Smart or Manual, plain toggle or Interruption alike — see
-- CONTEXT.md: Command, Interruption; ADR 0014. What was REQUESTED, as opposed to
-- plug_state_transition (what was actually observed) — a Smart Plug's Command may never be
-- confirmed at all if the device was unreachable when the owning Plugin tried to execute it.
-- Plug-scoped rather than folded into care_event: a Plug can be Room-owned instead of belonging to
-- any Enclosure, so care_event's NOT NULL enclosure_id wouldn't fit every row here. Append-only,
-- like sensor_reading/care_event — never updated in place.
CREATE TABLE IF NOT EXISTS plug_command_log (
    id              INTEGER PRIMARY KEY,
    plug_id         INTEGER NOT NULL REFERENCES plug(id) ON DELETE CASCADE,
    requested_at    TEXT NOT NULL DEFAULT (datetime('now')),
    is_on           INTEGER NOT NULL,  -- 0/1, the commanded state
    is_interruption INTEGER NOT NULL,  -- 0/1 — true iff the Plug had a determined setting at request time (see CONTEXT.md: Interruption)
    note            TEXT               -- optional; only ever prompted-for on an Interruption
);
CREATE INDEX IF NOT EXISTS idx_plug_command_log_plug_time ON plug_command_log (plug_id, requested_at);

-- Data Capture: a Plug's telemetry snapshot (watts/volts/amps), the Plug-side equivalent of a
-- Sensor's Reading (see CONTEXT.md: Data Capture, ADR 0009). Written on a slower, independent
-- cadence (every 1-5 min, a plain code constant like the poll interval — see ADR 0005's precedent)
-- from the 5-second on/off watch above, since wattage drifts continuously while a transition is
-- edge-triggered. Pulled from the same local tinytuya status() call already being made — no new
-- external dependency.
CREATE TABLE IF NOT EXISTS plug_reading (
    id                INTEGER PRIMARY KEY,
    plug_id           INTEGER NOT NULL REFERENCES plug(id) ON DELETE CASCADE,
    recorded_at       TEXT NOT NULL DEFAULT (datetime('now')),
    watts             REAL,
    volts             REAL,
    amps              REAL,
    countdown_seconds INTEGER  -- active countdown timer DPS, if any (0/NULL = none active)
);
CREATE INDEX IF NOT EXISTS idx_plug_reading_plug_time ON plug_reading (plug_id, recorded_at);

-- Per-Plug Alert state machine — see the sensor_alert_state comment above for why this is a
-- separate typed table rather than one polymorphic table shared with Sensors.
CREATE TABLE IF NOT EXISTS plug_alert_state (
    id               INTEGER PRIMARY KEY,
    plug_id          INTEGER NOT NULL REFERENCES plug(id) ON DELETE CASCADE,
    condition_kind   TEXT NOT NULL CHECK (condition_kind IN ('zero_power_while_on', 'unreachable')),
    state            TEXT NOT NULL DEFAULT 'normal' CHECK (state IN ('normal', 'pending', 'alerting', 'resolved')),
    state_entered_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (plug_id, condition_kind)
);

-- Manually-logged Care Events (see CONTEXT.md: Care Event, Feeding/Watering/Cleaning). Written by the web app (Phase 2).
-- animal_id is a Spot-feed only (see CONTEXT.md: Spot-feed) — NULL means the ordinary whole-Enclosure
-- case (every kind, and most Feedings); set only ever alongside kind = 'feeding', enforced in
-- web/admin_queries.py rather than a CHECK, same pattern as this file's other cross-column rules.
CREATE TABLE IF NOT EXISTS care_event (
    id            INTEGER PRIMARY KEY,
    enclosure_id  INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    animal_id     INTEGER REFERENCES animal(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('feeding', 'watering', 'spot_clean', 'deep_clean')),
    occurred_at   TEXT NOT NULL DEFAULT (datetime('now')),
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_care_event_enclosure_kind_time ON care_event (enclosure_id, kind, occurred_at);
