-- Husbandry Tracker schema.
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
    ingest_scan_interval_seconds   INTEGER NOT NULL DEFAULT 5,   -- see CONTEXT.md: Ingest; ADR 0013
    tuya_access_id                 TEXT,                         -- Tuya IoT Cloud project credentials — see ADR 0030
    tuya_access_secret             TEXT,                         -- never echoed back into any rendered page
    tuya_api_region                TEXT NOT NULL DEFAULT 'us'    -- one of: us, eu, cn, in
);
INSERT OR IGNORE INTO app_setting (id) VALUES (1);

-- Login/roles (see CONTEXT.md: User Account, Role, Session, Audit Log; ADR 0058; RHA-99 Phase 1).
-- is_active = 0 disables an account without losing its history (sessions, audit rows); the app
-- itself enforces "at least one active admin always exists" in code (web/auth_queries.py), not a
-- CHECK here, same pattern as every other cross-row invariant in this file.
CREATE TABLE IF NOT EXISTS user (
    id              INTEGER PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A logged-in session, keyed by the random token stored (HttpOnly, SameSite=Lax) in the browser's
-- cookie. No expires_at: the ticket's model is explicit revocation (logout, an admin resetting a
-- password, "sign out everywhere") rather than idle timeout, so a session lives until deleted.
CREATE TABLE IF NOT EXISTS session (
    token           TEXT PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_user ON session (user_id);

-- Login/logout/user-management audit trail (see CONTEXT.md: Audit Log) — also the source of truth
-- for rate-limiting failed logins (see web/auth_queries.py's is_rate_limited()), rather than a
-- separate counters table: a login dependency just counts recent login_failed rows by username
-- and by IP. actor_user_id is NULL for a failed/anonymous attempt; username_attempted is set only
-- on login_failed, when the typed username doesn't resolve to a real row.
CREATE TABLE IF NOT EXISTS audit_log (
    id                  INTEGER PRIMARY KEY,
    at                  TEXT NOT NULL DEFAULT (datetime('now')),
    actor_user_id       INTEGER REFERENCES user(id) ON DELETE SET NULL,
    username_attempted  TEXT,
    ip_address          TEXT,
    action              TEXT NOT NULL,  -- login_success | login_failed | logout | user_created |
                                         -- user_disabled | user_enabled | user_role_changed |
                                         -- password_reset | password_reset_tray
    detail              TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_at ON audit_log (action, at);

-- A named grouping of Enclosures sharing a physical space. See CONTEXT.md: Room, Light Schedule.
-- No Animals, Bioactive flag, or Care Events here — a Room isn't a housing unit, it's a grouping +
-- ambient-monitoring layer around one or more Enclosures.
CREATE TABLE IF NOT EXISTS room (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    light_on_time   TEXT,    -- "HH:MM", Light Schedule — both-or-neither with light_off_time
    light_off_time  TEXT,    -- "HH:MM"
    light_notes     TEXT,    -- free text, independent of whether a time is set
    -- Dashboard display order (see CONTEXT.md: Room) — user-set by dragging a Room section up/down
    -- on the dashboard (web/static/app.js's onRoomDrop); web/queries.py's get_dashboard_data()
    -- orders by this, not name. New Rooms default to 0 at the DB level but web/admin_queries.py's
    -- create_room() always overrides that to append at the end (max + 1), so 0 is never actually
    -- meaningful for a Room created through the app.
    sort_order      INTEGER NOT NULL DEFAULT 0,
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
    -- Whether each Care kind's pill shows in this Enclosure's Dashboard panel — same opt-in-per-item
    -- pattern as Animal/Sensor/Plug show_on_dashboard (see CONTEXT.md: Care Interval), just fixed to
    -- the 4 Care kinds instead of a variable-length list of rows. Defaults on for all 4 — Admin's own
    -- Care section (web/admin_queries.py's get_enclosure()) always lists every kind regardless.
    show_feeding_on_dashboard     INTEGER NOT NULL DEFAULT 1,
    show_watering_on_dashboard    INTEGER NOT NULL DEFAULT 1,
    show_spot_clean_on_dashboard  INTEGER NOT NULL DEFAULT 1,
    show_deep_clean_on_dashboard  INTEGER NOT NULL DEFAULT 1,
    -- Care Setup Prompt escalation (see CONTEXT.md: Care Setup Prompt, Care Interval; ADR 0040) —
    -- *_nag_count counts the separate calendar days a kind has been nagged about while still
    -- unlogged; once it reaches CARE_NAG_RED_THRESHOLD (web/status.py) the kind's Unknown ("no
    -- data") pill escalates to Red. *_nag_last_date dedupes same-day visits from double-counting.
    -- Both reset back to 0/NULL the moment that kind gets real data (see
    -- web/admin_queries.py's record_care_nags()).
    feeding_nag_count         INTEGER NOT NULL DEFAULT 0,
    feeding_nag_last_date     TEXT,
    watering_nag_count        INTEGER NOT NULL DEFAULT 0,
    watering_nag_last_date    TEXT,
    spot_clean_nag_count      INTEGER NOT NULL DEFAULT 0,
    spot_clean_nag_last_date  TEXT,
    deep_clean_nag_count      INTEGER NOT NULL DEFAULT 0,
    deep_clean_nag_last_date  TEXT,
    -- Enclosure Photo (see CONTEXT.md: Enclosure Photo) — same shape as animal.image_filename,
    -- just the filename under data/images/enclosures/; NULL means none uploaded.
    image_filename            TEXT,
    -- Dashboard Thumbnail (see CONTEXT.md: Dashboard Thumbnail) — which photo, if any, this
    -- Enclosure's own Dashboard panel shows: either its own Enclosure Photo, or one specific
    -- Animal's Photo (never both at once — see CONTEXT.md). dashboard_thumbnail_animal_id is only
    -- meaningful when the source is 'animal'; ON DELETE SET NULL (same pattern as
    -- fallback_sensor_id) means a deleted Animal just leaves the Dashboard panel with no thumbnail
    -- rather than an error — see web/queries.py's get_dashboard_data().
    dashboard_thumbnail_source     TEXT NOT NULL DEFAULT 'enclosure'
                                       CHECK (dashboard_thumbnail_source IN ('enclosure', 'animal')),
    dashboard_thumbnail_animal_id  INTEGER REFERENCES animal(id) ON DELETE SET NULL,
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
    -- The Species Profile key picked for this Animal in the Setup Wizard (see web/static/app.js's
    -- SPECIES_PROFILES, CONTEXT.md: Species Profile), NULL if none was picked or the Animal was
    -- added from the Enclosure's own Admin page instead (that form has no Species Profile picker).
    -- Lets a later "Add Sensor" on this Enclosure pre-fill its own Species Profile (RHA-94) without
    -- asking again — only when every Animal in the Enclosure that has one set agrees on the same
    -- value (see web/admin_queries.py's get_enclosure()).
    species_profile     TEXT,
    dob                 TEXT,  -- ISO date, nullable (not always known)
    -- Whether this Animal's card shows on the Dashboard's Enclosure panel — an Enclosure housing a
    -- colony can have more Animals than fit comfortably at a glance, so this is opt-in per Animal,
    -- toggled from the Enclosure's own Admin page. Defaults on; web/admin_queries.py's
    -- create_animal() only auto-enables it for the first 3 Animals in an Enclosure (see
    -- CONTEXT.md: Animal) — after that, a new Animal defaults off until the user picks it.
    show_on_dashboard   INTEGER NOT NULL DEFAULT 1,
    -- Animal Photo (see CONTEXT.md: Animal Photo) — just the filename (e.g. "14.jpg"), stored
    -- under data/images/animals/ (web/image_storage.py); NULL means no photo uploaded yet. One
    -- image per Animal, replaced wholesale on a new upload — never a history/gallery.
    image_filename      TEXT,
    -- Sex (see CONTEXT.md: Animal; RHA-102) on every Animal, corals and fish included. Always
    -- editable, since mis-sexing is common; Unknown until someone says otherwise. Must match
    -- web/queries.py's ANIMAL_SEXES.
    sex                 TEXT NOT NULL DEFAULT 'unknown' CHECK (sex IN ('male', 'female', 'unknown'))
);

-- A manually-logged, backdatable Animal Log entry (see CONTEXT.md: Animal Log) — Weight/Length/
-- Count/Condition are self-reported and independent of each other: a given entry normally fills in
-- just one of them (one metric, one occurrence), so all four stay nullable on one shared row rather
-- than splitting into four tables, same "many nullable metric columns, one row" shape as
-- sensor_reading. note is free text, usable on its own or alongside a Condition pick.
CREATE TABLE IF NOT EXISTS animal_log (
    id           INTEGER PRIMARY KEY,
    animal_id    INTEGER NOT NULL REFERENCES animal(id) ON DELETE CASCADE,
    weight_g     REAL,
    length_cm    REAL,
    count        INTEGER,
    condition    TEXT CHECK (condition IN ('poor', 'ok', 'good', 'really_good')),
    note         TEXT,
    occurred_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_animal_log_animal_time ON animal_log (animal_id, occurred_at);

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
    target_uvb_index_min  REAL,  -- UV Index, not raw irradiance — see schemas/enclosure_types.py
    target_uvb_index_max  REAL,
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
    -- Volatility (see CONTEXT.md: Volatility; ADR 0025) — Manual Sensor only, one nullable
    -- override per Target Range metric. NULL means "use that metric's own default_volatility"
    -- (schemas/enclosure_types.py's TargetRangeMetric) rather than defaulting here, so a fresh
    -- install's un-overridden Sensors still reflect a future code-level default change.
    volatility_temperature      TEXT CHECK (volatility_temperature IS NULL OR volatility_temperature IN ('fast', 'slow')),
    volatility_humidity         TEXT CHECK (volatility_humidity IS NULL OR volatility_humidity IN ('fast', 'slow')),
    volatility_uvb              TEXT CHECK (volatility_uvb IS NULL OR volatility_uvb IN ('fast', 'slow')),
    volatility_ph                TEXT CHECK (volatility_ph IS NULL OR volatility_ph IN ('fast', 'slow')),
    volatility_ammonia          TEXT CHECK (volatility_ammonia IS NULL OR volatility_ammonia IN ('fast', 'slow')),
    volatility_nitrite          TEXT CHECK (volatility_nitrite IS NULL OR volatility_nitrite IN ('fast', 'slow')),
    volatility_nitrate          TEXT CHECK (volatility_nitrate IS NULL OR volatility_nitrate IN ('fast', 'slow')),
    volatility_specific_gravity TEXT CHECK (volatility_specific_gravity IS NULL OR volatility_specific_gravity IN ('fast', 'slow')),
    volatility_salinity         TEXT CHECK (volatility_salinity IS NULL OR volatility_salinity IN ('fast', 'slow')),
    volatility_alkalinity       TEXT CHECK (volatility_alkalinity IS NULL OR volatility_alkalinity IN ('fast', 'slow')),
    volatility_calcium          TEXT CHECK (volatility_calcium IS NULL OR volatility_calcium IN ('fast', 'slow')),
    volatility_magnesium        TEXT CHECK (volatility_magnesium IS NULL OR volatility_magnesium IN ('fast', 'slow')),
    volatility_phosphate        TEXT CHECK (volatility_phosphate IS NULL OR volatility_phosphate IN ('fast', 'slow')),
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
-- target_on_time/target_off_time (plus optional target_on_time_2/3, target_off_time_2/3 — up to 3
-- on/off cycles total) hold the Target Schedule (see CONTEXT.md: Target Schedule, ADR 0012,
-- ADR 0057) — available on any Plug without a Controller Kind, Smart or Manual alike. For a Manual
-- Plug it's the only schedule info there is (nothing to observe). For a Smart Plug each detected
-- on/off time is compared against whichever cycle's target is nearest to it (the Detected Schedule
-- itself, computed from plug_state_transition, not stored, stays a single most-recent on-time and
-- off-time — not cycle-aware), flagged as a Timer Warning when they drift apart by more than
-- schedule_drift_threshold_minutes (app_setting). Superseded "Declared Schedule" from earlier
-- versions of this app, which only ever existed for a Manual Plug with no comparison possible.
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
-- A named container for several Plugs that are physically one multi-outlet Tuya device — see
-- CONTEXT.md: Plug Group, Plug Group Template, Always-On Outlet, All On / All Off; ADR 0017.
-- Purely organizational plus the shared All On/All Off action; it owns no polling/control state of
-- its own. Same Room-XOR-Enclosure-set ownership rule as `plug` itself (see that table's comment) —
-- room_id here, plug_group_enclosure below for the Enclosure side — enforced in
-- web/admin_queries.py, not a CHECK, for the same reason plug's own version isn't.
CREATE TABLE IF NOT EXISTS plug_group (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    room_id     INTEGER REFERENCES room(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Which Enclosure(s) a non-Room-owned Plug Group belongs to — mirrors plug_enclosure exactly (see
-- CONTEXT.md: Plug Group).
CREATE TABLE IF NOT EXISTS plug_group_enclosure (
    plug_group_id INTEGER NOT NULL REFERENCES plug_group(id) ON DELETE CASCADE,
    enclosure_id  INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    PRIMARY KEY (plug_group_id, enclosure_id)
);

-- The Room-XOR-Enclosure-set invariant can't be a single-table CHECK (it depends on plug_enclosure
-- row counts) — enforced in web/admin_queries.py instead, same pattern as Manual Sensor's Target
-- Range requirement.
CREATE TABLE IF NOT EXISTS plug (
    id                  INTEGER PRIMARY KEY,
    room_id             INTEGER REFERENCES room(id) ON DELETE CASCADE,
    -- Optional membership in a Plug Group (see CONTEXT.md: Plug Group; ADR 0017) — NULL for the
    -- common case of a standalone Plug. ON DELETE SET NULL: deleting a Group ungroups its members
    -- rather than deleting them (see CONTEXT.md: Plug Group).
    plug_group_id       INTEGER REFERENCES plug_group(id) ON DELETE SET NULL,
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
    -- "HH:MM", only ever set together with controller_kind = 'timer' (see CONTEXT.md: Target
    -- Schedule; RHA-95 split this out of 'none', which carries no schedule at all any more).
    -- This is Cycle 1 of up to 3 on/off cycles a Timer-Controlled Plug can carry — Cycles 2/3
    -- below are optional, contiguous (2 needs 1, 3 needs 2 — enforced in web/admin_queries.py, not
    -- a CHECK here, same as this table's other cross-column Plug rules) extensions of the same
    -- idea, for a Plug that cycles more than once a day (e.g. a basking light on twice, a misting
    -- pump three times).
    target_on_time      TEXT,
    target_off_time     TEXT,
    target_on_time_2    TEXT,
    target_off_time_2   TEXT,
    target_on_time_3    TEXT,
    target_off_time_3   TEXT,
    -- Always On (see CONTEXT.md: Always On) — e.g. a pump that runs continuously. Only meaningful
    -- when controller_kind = 'none'; enforced in web/admin_queries.py, not a CHECK here, same as
    -- this table's other cross-column Plug rules.
    always_on           INTEGER NOT NULL DEFAULT 0,
    -- Timer Warning acknowledgement (see CONTEXT.md: Timer Warning) — the Detected Schedule time the
    -- user cleared the warning against, per on/off time. NULL = never cleared. update_plug() resets
    -- both to NULL whenever the Target Schedule changes, since a cleared warning only means
    -- something against the target it was cleared under.
    timer_ack_on_time   TEXT,
    timer_ack_off_time  TEXT,
    -- 'timer' added by RHA-95 (tools/migrate_2026_10_29_plug_timer_controller_kind.py widens this
    -- CHECK on an already-deployed database, since SQLite can't ALTER one in place) — see
    -- CONTEXT.md: Controller Kind, Timer-Controlled, ADR 0008 (supersedes ADR 0007's
    -- is_thermostat_controlled).
    controller_kind     TEXT NOT NULL DEFAULT 'none' CHECK (controller_kind IN ('none', 'timer', 'thermostat', 'hydrostat')),
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
    uvb_index      REAL,
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

-- A free-form log entry from a Plugin or an AI skill (see CONTEXT.md: Log Event; ADR 0044) — the
-- generalization of the Inbox/Ingest contract beyond the three fixed observation kinds above.
-- source is the plugin/skill name (matches a Plugin Event's own `plugin` field); scope is that
-- event's external_id, repurposed here as a free-form reference (e.g. "enclosure:3", "animal:12",
-- or "app" when the entry isn't about any specific entity) rather than a Registry-matched device
-- id — Ingest writes every log event straight through, unlike sensor_reading/plug_state/
-- plug_telemetry, which are dropped if external_id doesn't resolve to a registered Sensor/Plug.
CREATE TABLE IF NOT EXISTS event_log (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    scope       TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'info' CHECK (level IN ('debug', 'info', 'warning', 'error')),
    message     TEXT NOT NULL,
    data        TEXT,  -- opaque JSON, NULL if the event carried none
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_event_log_source_time ON event_log (source, recorded_at);
CREATE INDEX IF NOT EXISTS idx_event_log_scope_time ON event_log (scope, recorded_at);

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

-- A 1:1 extension of a Feeding care_event (see CONTEXT.md: Feeding Detail; ADR 0042) — the richer
-- fields a Feeding Care Event never had room for. Deliberately NOT a replacement for care_event:
-- Feeding's Care Interval/staleness/nag tracking stays on the shared care_event mechanism Watering/
-- Spot-clean/Deep-clean also use, so this only carries what's new. note stays on care_event itself
-- rather than being duplicated here. care_event_id is UNIQUE — exactly one Feeding Detail per
-- Feeding care_event, cascade-deleted if that row ever is.
CREATE TABLE IF NOT EXISTS feeding_detail (
    id            INTEGER PRIMARY KEY,
    care_event_id INTEGER NOT NULL UNIQUE REFERENCES care_event(id) ON DELETE CASCADE,
    food          TEXT,     -- free text, e.g. "frozen-thawed rat - small" — type and size fuse together in real use
    count         INTEGER,
    prey_state    TEXT CHECK (prey_state IN ('live', 'frozen_thawed', 'dry')),
    result        TEXT NOT NULL DEFAULT 'accepted' CHECK (result IN ('accepted', 'refused'))
);

-- A manually-logged, backdatable Shed observation for one Animal (see CONTEXT.md: Shed Log; ADR
-- 0042) — not a Care Event: nothing was "done," and there's no interval/staleness tracking for
-- it, same reasoning plant_health_log and animal_log already use. stuck_locations is Partial-only,
-- a comma-joined list of SHED_STUCK_LOCATIONS codes (web/queries.py) plus optional free text —
-- flat TEXT, not a join table, same simplicity bias as every other small multi-value field in this
-- schema; nothing needs to query across Animals by stuck-location yet.
CREATE TABLE IF NOT EXISTS shed_log (
    id              INTEGER PRIMARY KEY,
    animal_id       INTEGER NOT NULL REFERENCES animal(id) ON DELETE CASCADE,
    completeness    TEXT NOT NULL CHECK (completeness IN ('full', 'partial')),
    stuck_locations TEXT,
    note            TEXT,
    occurred_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_shed_log_animal_time ON shed_log (animal_id, occurred_at);

-- Species Profile Knowledge Base (see CONTEXT.md: Knowledge Base, Species Profile; ADR 0054) — 7
-- editable reference tables, one per schemas/species_profile_kb.py ProfileCategory, replacing the
-- old hardcoded, never-persisted SPECIES_PROFILES literal in web/static/app.js. Each is a separate
-- table (not one polymorphic table with a category column) for the same reason sensor_alert_state's
-- comment gives: this schema always prefers an explicit typed table per entity kind, and the 7
-- categories genuinely need different columns (water chemistry vs. basking/humidity).
--
-- profile_key is what's carried onto `animal.species_profile` and the Setup/Add-Pet Wizards' own
-- query-string chain (see Animal, Species Profile) — kept identical to the pre-Knowledge-Base
-- SPECIES_PROFILES dict keys for snake_profile/lizard_profile specifically, so an already-stored
-- Animal row's species_profile value keeps resolving to the same row after migration (see
-- tools/migrate_2026_11_02_species_profile_kb.py). notes is free-text sources/citations, matching
-- the Source column docs/reference/Reptile Care Parameters Knowledge Base.md already has — that
-- markdown file is left untouched as a historical snapshot; this is the live, editable version.
-- sort_order is append-at-the-end on create, same pattern as room.sort_order.
CREATE TABLE IF NOT EXISTS snake_profile (
    id                          INTEGER PRIMARY KEY,
    profile_key                 TEXT NOT NULL UNIQUE,
    common_name                 TEXT NOT NULL,
    scientific_name             TEXT,
    basking_min_f               REAL,
    basking_max_f               REAL,
    cool_min_f                  REAL,
    cool_max_f                  REAL,
    night_min_f                 REAL,
    night_max_f                 REAL,
    humidity_min_pct            REAL,
    humidity_max_pct            REAL,
    feeding_baby_interval_days  INTEGER,
    feeding_adult_interval_days INTEGER,
    notes                       TEXT,
    sort_order                  INTEGER NOT NULL DEFAULT 0,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lizard_profile (
    id                          INTEGER PRIMARY KEY,
    profile_key                 TEXT NOT NULL UNIQUE,
    common_name                 TEXT NOT NULL,
    scientific_name             TEXT,
    basking_min_f               REAL,
    basking_max_f               REAL,
    cool_min_f                  REAL,
    cool_max_f                  REAL,
    night_min_f                 REAL,
    night_max_f                 REAL,
    humidity_min_pct            REAL,
    humidity_max_pct            REAL,
    feeding_baby_interval_days  INTEGER,
    feeding_adult_interval_days INTEGER,
    notes                       TEXT,
    sort_order                  INTEGER NOT NULL DEFAULT 0,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Pet insects (mantids, beetles, roaches kept as pets, stick insects, etc.) — distinct from feeder
-- insects, which this app has no tracking concept for at all (see CONTEXT.md: Knowledge Base).
CREATE TABLE IF NOT EXISTS insect_profile (
    id                INTEGER PRIMARY KEY,
    profile_key       TEXT NOT NULL UNIQUE,
    common_name       TEXT NOT NULL,
    scientific_name   TEXT,
    temp_min_f        REAL,
    temp_max_f        REAL,
    humidity_min_pct  REAL,
    humidity_max_pct  REAL,
    lifespan          TEXT,
    diet              TEXT,
    notes             TEXT,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saltwater_fish_profile (
    id                INTEGER PRIMARY KEY,
    profile_key       TEXT NOT NULL UNIQUE,
    common_name       TEXT NOT NULL,
    scientific_name   TEXT,
    temp_min_f        REAL,
    temp_max_f        REAL,
    salinity_sg_min   REAL,
    salinity_sg_max   REAL,
    ph_min            REAL,
    ph_max            REAL,
    ammonia_ppm_max   REAL,
    nitrite_ppm_max   REAL,
    nitrate_ppm_max   REAL,
    diet              TEXT,
    notes             TEXT,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS freshwater_fish_profile (
    id                INTEGER PRIMARY KEY,
    profile_key       TEXT NOT NULL UNIQUE,
    common_name       TEXT NOT NULL,
    scientific_name   TEXT,
    temp_min_f        REAL,
    temp_max_f        REAL,
    ph_min            REAL,
    ph_max            REAL,
    gh_min            REAL,
    gh_max            REAL,
    kh_min            REAL,
    kh_max            REAL,
    ammonia_ppm_max   REAL,
    nitrite_ppm_max   REAL,
    nitrate_ppm_max   REAL,
    diet              TEXT,
    notes             TEXT,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saltwater_invert_profile (
    id                  INTEGER PRIMARY KEY,
    profile_key         TEXT NOT NULL UNIQUE,
    common_name         TEXT NOT NULL,
    scientific_name     TEXT,
    temp_min_f          REAL,
    temp_max_f          REAL,
    salinity_sg_min     REAL,
    salinity_sg_max     REAL,
    ph_min              REAL,
    ph_max              REAL,
    alkalinity_dkh_min  REAL,
    alkalinity_dkh_max  REAL,
    calcium_ppm_min     REAL,
    calcium_ppm_max     REAL,
    diet                TEXT,
    notes               TEXT,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS freshwater_invert_profile (
    id                  INTEGER PRIMARY KEY,
    profile_key         TEXT NOT NULL UNIQUE,
    common_name         TEXT NOT NULL,
    scientific_name     TEXT,
    temp_min_f          REAL,
    temp_max_f          REAL,
    ph_min              REAL,
    ph_max              REAL,
    gh_min              REAL,
    gh_max              REAL,
    kh_min              REAL,
    kh_max              REAL,
    diet                TEXT,
    sensitivity_notes   TEXT,
    notes               TEXT,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Seed data: Snakes/Lizards migrated unchanged from the retired SPECIES_PROFILES literal (ADR
-- 0054) — same keys, same numbers, same order. Feeding intervals were already collapsed to a
-- rounded midpoint there (e.g. "every 5-7 days" -> 6); kept that way here rather than re-expanding
-- to a range, since `animal`/`enclosure`.feeding_interval_days is itself a single integer.
INSERT OR IGNORE INTO snake_profile
    (profile_key, common_name, scientific_name, basking_min_f, basking_max_f, cool_min_f, cool_max_f, night_min_f, night_max_f, humidity_min_pct, humidity_max_pct, feeding_baby_interval_days, feeding_adult_interval_days, notes, sort_order)
VALUES
    ('ball_python', 'Ball Python', 'Python regius', 88, 95, 75, 80, 72, 78, 50, 70, 6, 21, 'ReptiFiles, PetMD', 0),
    ('corn_snake', 'Corn Snake', 'Pantherophis guttatus', 85, 90, 72, 78, 65, 70, 40, 60, 6, 16, 'ReptiFiles, Phoenix Herp', 1),
    ('california_kingsnake', 'California Kingsnake', 'Lampropeltis californiae', 85, 90, 70, 80, 65, 70, 40, 60, 6, 11, 'Phoenix Herp, Josh''s Frogs', 2),
    ('western_hognose', 'Western Hognose Snake', 'Heterodon nasicus', 90, 95, 70, 75, 60, 75, 30, 50, 6, 12, 'ReptiFiles, Bio Dude', 3),
    ('boa_constrictor', 'Boa Constrictor', 'Boa constrictor, Boa imperator', 88, 95, 75, 80, 72, 78, 60, 70, 9, 21, 'ReptiFiles, Dubia', 4),
    ('honduran_milk_snake', 'Honduran Milk Snake', 'Lampropeltis hondurensis', 85, 88, 72, 78, 65, 75, 40, 60, 6, 11, 'Bio Dude, FurryCritter', 5),
    ('rosy_boa', 'Rosy Boa', 'Lichanura trivirgata', 90, 95, 75, 85, 65, 70, 30, 50, 9, 16, 'ReptiFiles, That Pet Place', 6),
    ('kenyan_sand_boa', 'Kenyan Sand Boa', 'Eryx colubrinus', 90, 95, 75, 80, 70, 75, 30, 50, 6, 21, 'ReptiFiles, Bio Dude', 7),
    ('gopher_snake', 'Gopher Snake / Bullsnake', 'Pituophis catenifer', 85, 90, 75, 80, 65, 70, 30, 50, 6, 11, 'Dubia, Reptiles Magazine', 8),
    ('carpet_python', 'Carpet Python', 'Morelia spilota', 88, 95, 75, 80, 70, 75, 50, 60, 9, 18, 'Dubia, Shadows Reptiles', 9),
    ('snake_other', 'Snake (other/unlisted)', NULL, 85, 95, 70, 80, 65, 75, 30, 70, 7, 14, 'Consensus range across the listed snakes above — deliberately wide, pick a named species if possible.', 10);

INSERT OR IGNORE INTO lizard_profile
    (profile_key, common_name, scientific_name, basking_min_f, basking_max_f, cool_min_f, cool_max_f, night_min_f, night_max_f, humidity_min_pct, humidity_max_pct, feeding_baby_interval_days, feeding_adult_interval_days, notes, sort_order)
VALUES
    ('bearded_dragon', 'Bearded Dragon', 'Pogona vitticeps', 105, 115, 70, 85, 60, 72, 30, 40, 1, 1, 'ReptiFiles, PetSmart', 0),
    ('leopard_gecko', 'Leopard Gecko', 'Eublepharis macularius', 90, 95, 70, 80, 60, 75, 30, 40, 1, 3, 'Bio Dude, PetSmart', 1),
    ('crested_gecko', 'Crested Gecko', 'Correlophus ciliatus', 78, 82, 70, 75, 65, 72, 60, 80, 1, 2, 'Zen Habitats, Fluker''s', 2),
    ('blue_tongue_skink', 'Blue-Tongued Skink', 'Tiliqua scincoides intermedia', 105, 115, 70, 80, 65, 75, 40, 60, 1, 2, 'ReptiFiles, Bio Dude', 3),
    ('african_fat_tailed_gecko', 'African Fat-Tailed Gecko', 'Hemitheconyx caudicinctus', 88, 92, 70, 80, 70, 75, 50, 70, 1, 2, 'Dubia, WebMD', 4),
    ('veiled_chameleon', 'Veiled Chameleon', 'Chamaeleo calyptratus', 85, 90, 72, 78, 55, 65, 30, 50, 1, 2, 'ReptiFiles, Dubia', 5),
    ('gargoyle_gecko', 'Gargoyle Gecko', 'Rhacodactylus auriculatus', 82, 85, 70, 75, 65, 72, 50, 70, 1, 2, 'Bio Dude, Josh''s Frogs', 6),
    ('tegu', 'Argentine Black and White Tegu', 'Salvator merianae', 120, 135, 75, 85, 70, 75, 60, 80, 1, 3, 'ReptiFiles, LafeberVet', 7),
    ('green_iguana', 'Green Iguana', 'Iguana iguana', 115, 125, 75, 85, 73, 80, 60, 80, 1, 1, 'ReptiFiles, Chewy', 8),
    ('uromastyx', 'Uromastyx', 'Uromastyx spp.', 120, 130, 80, 85, 70, 80, 10, 35, 1, 1, 'ReptiFiles, That Pet Place', 9),
    ('lizard_other', 'Lizard (other/unlisted)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Deliberately left blank — the ten listed lizards alone span a 78-135°F basking range, so a single averaged number would be unsafe. Pick a named species if at all possible.', 10);

-- Seed data: Insects, and the 4 aquatic categories, researched fresh for this Knowledge Base (ADR
-- 0054) — hobbyist care-sheet consensus ranges, same rigor as the original Snakes/Lizards research
-- but without a per-row citation trail (no specific source was pinned per figure the way the
-- original markdown doc did) — treat as a documented starting point to verify/adjust, same caveat
-- the original doc's own "Ranges are consensus, not law" note already carries.
INSERT OR IGNORE INTO insect_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, humidity_min_pct, humidity_max_pct, lifespan, diet, notes, sort_order)
VALUES
    ('chinese_mantis', 'Chinese Mantis', 'Tenodera sinensis', 70, 85, 50, 70, '~1 year, egg to adult death', 'Live insects (flies, crickets) — daily as a nymph, 2-3x/week as an adult', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('orchid_mantis', 'Orchid Mantis', 'Hymenopus coronatus', 75, 85, 70, 80, '~6-8 months', 'Live flying insects several times a week', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('ghost_mantis', 'Ghost Mantis', 'Phyllocrania paradoxa', 72, 82, 60, 75, '~8-10 months', 'Small live flying insects, 2-3x/week as an adult', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('deaths_head_cockroach', 'Death''s Head Cockroach', 'Blaberus craniifer', 75, 85, 50, 70, '1-2 years as an adult', 'Fruit, vegetables, and protein (fish flakes or dry dog food)', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('madagascar_hissing_cockroach', 'Madagascar Hissing Cockroach', 'Gromphadorhina portentosa', 75, 85, 60, 80, '2-5 years', 'Fruit, vegetables, and protein (fish flakes or dry dog food)', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('hercules_beetle', 'Hercules Beetle', 'Dynastes hercules', 72, 82, 70, 80, '~1 year as an adult (longer as larva)', 'Larva: rotting wood/substrate. Adult: soft fruit.', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('indian_stick_insect', 'Indian Stick Insect', 'Carausius morosus', 68, 80, 50, 70, '~1 year', 'Bramble, ivy, or privet leaves daily', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('macleays_spectre', 'Macleay''s Spectre (Giant Stick Insect)', 'Extatosoma tiaratum', 72, 82, 60, 80, '~18 months', 'Eucalyptus or bramble leaves daily', 'Care-sheet consensus (hobbyist reference ranges).', 7),
    ('insect', 'Insect (other/unlisted)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Deliberately left blank — "Insect" spans far too much (mantids, beetles, roaches, stick insects) for one averaged range. Pick a named species if at all possible.', 8);

INSERT OR IGNORE INTO saltwater_fish_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, salinity_sg_min, salinity_sg_max, ph_min, ph_max, ammonia_ppm_max, nitrite_ppm_max, nitrate_ppm_max, diet, notes, sort_order)
VALUES
    ('clownfish', 'Ocellaris Clownfish', 'Amphiprion ocellaris', 74, 82, 1.020, 1.025, 8.1, 8.4, 0, 0, 10, 'Omnivore — flake/frozen mysis, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('banggai_cardinalfish', 'Banggai Cardinalfish', 'Pterapogon kauderni', 75, 82, 1.020, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — mysis/flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('royal_gramma', 'Royal Gramma', 'Gramma loreto', 72, 78, 1.020, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — mysis/flake, 1x/day', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('firefish_goby', 'Firefish Goby', 'Nemateleotris magnifica', 72, 78, 1.020, 1.024, 8.1, 8.4, 0, 0, 10, 'Carnivore — small meaty foods, 2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('blue_green_chromis', 'Blue-Green Chromis', 'Chromis viridis', 72, 78, 1.020, 1.025, 8.1, 8.4, 0, 0, 15, 'Omnivore — flake/frozen, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('yellow_tang', 'Yellow Tang', 'Zebrasoma flavescens', 72, 78, 1.023, 1.025, 8.1, 8.4, 0, 0, 10, 'Herbivore — nori/algae sheet, daily', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('six_line_wrasse', 'Six-Line Wrasse', 'Pseudocheilinus hexataenia', 72, 78, 1.021, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — varied small meaty foods, daily', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('mandarinfish', 'Mandarinfish', 'Synchiropus splendidus', 72, 78, 1.021, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — live pods/frozen mysis, several small feedings/day; needs an established tank', 'Care-sheet consensus (hobbyist reference ranges).', 7);

INSERT OR IGNORE INTO freshwater_fish_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, ph_min, ph_max, gh_min, gh_max, kh_min, kh_max, ammonia_ppm_max, nitrite_ppm_max, nitrate_ppm_max, diet, notes, sort_order)
VALUES
    ('neon_tetra', 'Neon Tetra', 'Paracheirodon innesi', 72, 78, 6.0, 7.0, 2, 10, 2, 5, 0, 0, 20, 'Omnivore — flake/micro pellets, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('betta', 'Betta', 'Betta splendens', 76, 82, 6.5, 7.5, 5, 15, 3, 8, 0, 0, 20, 'Carnivore — pellets, 1x/day', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('guppy', 'Guppy', 'Poecilia reticulata', 72, 82, 7.0, 8.0, 8, 20, 4, 10, 0, 0, 20, 'Omnivore — flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('platy', 'Platy', 'Xiphophorus maculatus', 70, 78, 7.0, 8.2, 10, 28, 5, 15, 0, 0, 20, 'Omnivore — flake/veg, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('zebra_danio', 'Zebra Danio', 'Danio rerio', 64, 75, 6.5, 7.5, 5, 12, 4, 8, 0, 0, 20, 'Omnivore — flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('cherry_barb', 'Cherry Barb', 'Puntius titteya', 73, 79, 6.0, 7.5, 2, 12, 1, 5, 0, 0, 20, 'Omnivore — flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('corydoras_catfish', 'Corydoras Catfish', 'Corydoras spp.', 72, 78, 6.5, 7.5, 2, 12, 2, 5, 0, 0, 20, 'Omnivore, bottom feeder — sinking pellets, daily', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('angelfish', 'Angelfish', 'Pterophyllum scalare', 76, 84, 6.5, 7.5, 3, 8, 2, 5, 0, 0, 20, 'Omnivore — flake/pellets, 1x/day', 'Care-sheet consensus (hobbyist reference ranges).', 7);

INSERT OR IGNORE INTO saltwater_invert_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, salinity_sg_min, salinity_sg_max, ph_min, ph_max, alkalinity_dkh_min, alkalinity_dkh_max, calcium_ppm_min, calcium_ppm_max, diet, notes, sort_order)
VALUES
    ('cleaner_shrimp', 'Skunk Cleaner Shrimp', 'Lysmata amboinensis', 74, 82, 1.020, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Scavenger/omnivore — meaty foods and tank leftovers', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('peppermint_shrimp', 'Peppermint Shrimp', 'Lysmata wurdemanni', 74, 82, 1.020, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Omnivore — meaty foods; also eats Aiptasia anemones', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('blue_leg_hermit_crab', 'Blue Leg Hermit Crab', 'Clibanarius tricolor', 74, 82, 1.020, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Omnivore scavenger — algae and tank leftovers', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('emerald_crab', 'Emerald Crab', 'Mithraculus sculptus', 74, 82, 1.022, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Herbivore — algae grazer', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('turbo_snail', 'Turbo Snail', 'Turbo spp.', 74, 82, 1.022, 1.026, 8.1, 8.4, 8, 12, 380, 450, 'Herbivore — algae grazer', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('feather_duster_worm', 'Feather Duster Worm', 'Bispira spp.', 74, 82, 1.022, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Filter feeder — phytoplankton', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('green_star_polyp', 'Green Star Polyp', 'Pachyclavularia violacea', 75, 82, 1.023, 1.025, 8.1, 8.4, 8, 11, 400, 450, 'Photosynthetic (coral) — occasional target feeding helps but isn''t required', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('condylactis_anemone', 'Condylactis Anemone', 'Condylactis gigantea', 75, 82, 1.023, 1.025, 8.1, 8.4, 8, 12, 400, 450, 'Carnivore — meaty foods, 2-3x/week', 'Care-sheet consensus (hobbyist reference ranges).', 7);

INSERT OR IGNORE INTO freshwater_invert_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, ph_min, ph_max, gh_min, gh_max, kh_min, kh_max, diet, sensitivity_notes, notes, sort_order)
VALUES
    ('cherry_shrimp', 'Cherry Shrimp', 'Neocaridina davidi', 65, 78, 6.5, 8.0, 6, 10, 2, 6, 'Omnivore — algae and biofilm grazer', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('crystal_red_shrimp', 'Crystal Red Shrimp', 'Caridina cf. cantonensis', 65, 73, 6.0, 6.8, 4, 6, 0, 2, 'Omnivore — biofilm and specialized shrimp food', 'Copper-sensitive; needs very stable water parameters.', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('amano_shrimp', 'Amano Shrimp', 'Caridina multidentata', 64, 78, 6.5, 7.5, 6, 8, 2, 6, 'Algae grazer', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('nerite_snail', 'Nerite Snail', 'Neritina natalensis', 72, 78, 7.0, 8.0, 8, 15, 4, 10, 'Algae grazer', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('mystery_snail', 'Mystery Snail', 'Pomacea bridgesii', 68, 82, 7.0, 8.0, 8, 18, 4, 10, 'Omnivore — algae and vegetables', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('malaysian_trumpet_snail', 'Malaysian Trumpet Snail', 'Melanoides tuberculata', 70, 80, 7.0, 8.0, 6, 15, 3, 8, 'Detritivore — substrate scavenger', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('dwarf_crayfish', 'Dwarf Crayfish (CPO)', 'Cambarellus patzcuarensis', 68, 78, 6.5, 8.0, 6, 15, 3, 8, 'Omnivore scavenger', 'Copper-sensitive; semi-aggressive toward small tankmates.', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('assassin_snail', 'Assassin Snail', 'Clea helena', 70, 78, 7.0, 8.0, 8, 15, 3, 8, 'Carnivore — eats pest snails', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 7);

-- Gene Catalog (see CONTEXT.md: Gene, Gene Catalog; RHA-104): the Genes each specific Knowledge
-- Base species can carry, editable from App Admin. A Gene points at its species by Knowledge Base
-- category key + profile_key (stable across renames; the 7 KB tables share no single id to
-- reference). Names are unique per species, case-insensitively; the same name in another species
-- is a different Gene. Seeded once by db/migrations/m0028_gene_catalog.py, not here, so a deleted
-- seed Gene stays deleted. inheritance must match web/gene_catalog_queries.py's INHERITANCES.
CREATE TABLE IF NOT EXISTS gene (
    id                  INTEGER PRIMARY KEY,
    species_category    TEXT NOT NULL,
    species_key         TEXT NOT NULL,
    name                TEXT NOT NULL COLLATE NOCASE,
    inheritance         TEXT NOT NULL CHECK (inheritance IN ('recessive', 'co_dominant', 'dominant')),
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (species_category, species_key, name)
);
