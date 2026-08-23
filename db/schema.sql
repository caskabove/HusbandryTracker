-- HerpMonitor schema.
-- Terminology matches CONTEXT.md — read that first if a name here is surprising.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS enclosure (
    id                        INTEGER PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
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

-- A Govee H5074 assigned to an Enclosure. See CONTEXT.md: Sensor, Target Range.
CREATE TABLE IF NOT EXISTS sensor (
    id                  INTEGER PRIMARY KEY,
    enclosure_id        INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    label               TEXT NOT NULL,             -- e.g. "warm side", "cool side"
    mac_address         TEXT NOT NULL UNIQUE,       -- e.g. "A4:C1:38:XX:XX:XX"
    target_temp_min_c   REAL,
    target_temp_max_c   REAL,
    target_humidity_min REAL,
    target_humidity_max REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A Gosund plug assigned to an Enclosure. See CONTEXT.md: Plug, Purpose.
--
-- Not every physical Tuya device is a single-outlet plug: multi-outlet power strips expose
-- several independently-switched DPS keys (e.g. "1"/"2"/"3" for three AC outlets, "7" for a USB
-- port) on ONE device_id. Each outlet is its own Plug row here, sharing the same device_id/
-- local_key/ip but a different switch_dps_key — hence the unique constraint being on the pair,
-- not on tuya_device_id alone.
CREATE TABLE IF NOT EXISTS plug (
    id              INTEGER PRIMARY KEY,
    enclosure_id    INTEGER NOT NULL REFERENCES enclosure(id) ON DELETE CASCADE,
    label           TEXT NOT NULL,                  -- e.g. "basking bulb", "UTH"
    purpose         TEXT NOT NULL CHECK (purpose IN ('light', 'heat', 'cooling')),
    tuya_device_id  TEXT NOT NULL,
    tuya_local_key  TEXT NOT NULL,
    tuya_ip_address TEXT,                           -- optional pin; tinytuya can also auto-discover on LAN
    switch_dps_key  TEXT NOT NULL DEFAULT '1',      -- which outlet on the device this Plug controls
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tuya_device_id, switch_dps_key)
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
