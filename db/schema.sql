-- HerpMonitor schema.
-- Terminology matches CONTEXT.md — read that first if a name here is surprising.

PRAGMA foreign_keys = ON;

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

CREATE TABLE IF NOT EXISTS enclosure (
    id                        INTEGER PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
    room_id                   INTEGER REFERENCES room(id) ON DELETE SET NULL,  -- optional (see CONTEXT.md: Room)
    fallback_sensor_id        INTEGER REFERENCES sensor(id) ON DELETE SET NULL,  -- see CONTEXT.md: Fallback Sensor
    bioactive                 INTEGER NOT NULL DEFAULT 0,   -- 0/1, informational only (see CONTEXT.md: Bioactive)
    feeding_interval_days     INTEGER NOT NULL DEFAULT 7,
    watering_interval_days    INTEGER NOT NULL DEFAULT 3,
    spot_clean_interval_days  INTEGER NOT NULL DEFAULT 7,
    deep_clean_interval_days  INTEGER NOT NULL DEFAULT 30,
    created_at                TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS animal (
    id                  INTEGER PRIMARY KEY,
    enclosure_id        INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    species_common      TEXT,
    species_scientific  TEXT,
    dob                 TEXT   -- ISO date, nullable (not always known)
);

-- A Sensor assigned to either an Enclosure or a Room, never both. See CONTEXT.md: Sensor,
-- Tracking Mode, Target Range, Room.
--
-- tracking_mode = 'smart': a real Govee H5074 BLE device, polled automatically — mac_address
-- required. tracking_mode = 'manual': no physical device — mac_address stays NULL, and Readings
-- are hand-logged through the Admin UI instead. A Manual Sensor must have a complete Target Range
-- (min AND max) on at least one metric before it's useful, but which metric is up to the user (an
-- IR thermometer spot-check has no humidity number to give) — that "at least one" rule is enforced
-- in web/admin_queries.py with a friendly error, not here, so a bad value gets a clear message
-- instead of a raw SQLite CHECK failure.
CREATE TABLE IF NOT EXISTS sensor (
    id                  INTEGER PRIMARY KEY,
    enclosure_id        INTEGER REFERENCES enclosure(id) ON DELETE CASCADE,
    room_id             INTEGER REFERENCES room(id) ON DELETE CASCADE,
    label               TEXT NOT NULL,             -- e.g. "warm side", "cool side"
    tracking_mode       TEXT NOT NULL DEFAULT 'smart' CHECK (tracking_mode IN ('smart', 'manual')),
    mac_address         TEXT UNIQUE,               -- e.g. "A4:C1:38:XX:XX:XX"; NULL for Manual
    target_temp_min_c   REAL,
    target_temp_max_c   REAL,
    target_humidity_min REAL,
    target_humidity_max REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (
        (tracking_mode = 'smart' AND mac_address IS NOT NULL) OR
        (tracking_mode = 'manual' AND mac_address IS NULL)
    ),
    CHECK (
        (enclosure_id IS NOT NULL AND room_id IS NULL) OR
        (enclosure_id IS NULL AND room_id IS NOT NULL)
    )
);

-- A Plug assigned to an Enclosure. See CONTEXT.md: Plug, Purpose, Tracking Mode, Schedule.
--
-- tracking_mode = 'smart': a real Tuya-controlled Gosund plug, polled automatically — Tuya
-- credentials required. tracking_mode = 'manual': no device, e.g. a mechanical timer — the Tuya
-- fields stay NULL and declared_on_time/declared_off_time hold the Declared Schedule the user
-- entered instead of one inferred from observed transitions.
--
-- Not every physical Tuya device is a single-outlet plug: multi-outlet power strips expose
-- several independently-switched DPS keys (e.g. "1"/"2"/"3" for three AC outlets, "7" for a USB
-- port) on ONE device_id. Each outlet is its own Plug row here, sharing the same device_id/
-- local_key/ip but a different switch_dps_key — hence the unique constraint being on the pair,
-- not on tuya_device_id alone. Manual Plugs all have tuya_device_id NULL, which SQLite treats as
-- distinct per row in a UNIQUE index, so multiple Manual Plugs never collide on that constraint.
CREATE TABLE IF NOT EXISTS plug (
    id                  INTEGER PRIMARY KEY,
    enclosure_id        INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    label               TEXT NOT NULL,                  -- e.g. "basking bulb", "UTH"
    purpose             TEXT NOT NULL CHECK (length(purpose) > 0),  -- free text; Admin suggests common values, doesn't restrict to them
    tracking_mode       TEXT NOT NULL DEFAULT 'smart' CHECK (tracking_mode IN ('smart', 'manual')),
    tuya_device_id      TEXT,
    tuya_local_key      TEXT,
    tuya_ip_address     TEXT,                           -- optional pin; tinytuya can also auto-discover on LAN
    switch_dps_key      TEXT NOT NULL DEFAULT '1',      -- which outlet on the device this Plug controls
    declared_on_time    TEXT,                           -- "HH:MM", Manual Plug only (see CONTEXT.md: Schedule)
    declared_off_time   TEXT,                           -- "HH:MM", Manual Plug only
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tuya_device_id, switch_dps_key),
    CHECK (
        (tracking_mode = 'smart' AND tuya_device_id IS NOT NULL AND tuya_local_key IS NOT NULL) OR
        (tracking_mode = 'manual' AND tuya_device_id IS NULL AND tuya_local_key IS NULL)
    )
);

-- Raw Sensor readings, captured continuously (see CONTEXT.md decision: capture everything, no charts in v1).
CREATE TABLE IF NOT EXISTS sensor_reading (
    id            INTEGER PRIMARY KEY,
    sensor_id     INTEGER NOT NULL REFERENCES sensor(id) ON DELETE CASCADE,
    recorded_at   TEXT NOT NULL DEFAULT (datetime('now')),
    temperature_c REAL,
    humidity_pct  REAL,
    battery_pct   INTEGER
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

-- Manually-logged Care Events (see CONTEXT.md: Care Event, Feeding/Watering/Cleaning). Written by the web app (Phase 2).
CREATE TABLE IF NOT EXISTS care_event (
    id            INTEGER PRIMARY KEY,
    enclosure_id  INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('feeding', 'watering', 'spot_clean', 'deep_clean')),
    occurred_at   TEXT NOT NULL DEFAULT (datetime('now')),
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_care_event_enclosure_kind_time ON care_event (enclosure_id, kind, occurred_at);
