"""Ordered registry of schema migrations, applied by db/migrate.py's run_migrations() (RHA-101;
ADR 0059).

Adding one: create the next mNNNN_<name>.py with a migrate(conn) function and append it below.
Imports are explicit, not discovered at runtime, so PyInstaller bundles every module (ADR 0018).

Rules for a migration:
- Idempotent: check the current shape (PRAGMA table_info, etc.) and skip work already done. The
  runner relies on this to bring any existing database, whatever it has or hasn't had, to the
  latest version (1-26 were the hand-run tools/migrate_* scripts, which may or may not have been
  run on a given database).
- Change the schema of tables that already exist. Brand-new tables need no migration; schema.sql
  creates them (CREATE TABLE IF NOT EXISTS). A migration may still call schema.sql itself when a
  later step depends on a new table existing.
- schema.sql is replayed by the runner after every migration commits, so a migration never needs
  to do that last step itself (1-26 still do; it's harmless).
- Never edit or renumber one that has shipped. Fix forward with a new migration.
"""
from __future__ import annotations

from collections.abc import Callable
import sqlite3

from db.migrations import m0001_action_tracking
from db.migrations import m0002_plugin_architecture
from db.migrations import m0003_target_schedule
from db.migrations import m0004_animal_dashboard_visibility
from db.migrations import m0005_plug_dashboard_visibility
from db.migrations import m0006_sensor_dashboard_visibility
from db.migrations import m0007_sensor_reading_metrics
from db.migrations import m0008_plug_always_on
from db.migrations import m0009_salinity_specific_gravity
from db.migrations import m0010_plug_group
from db.migrations import m0011_uvb_index
from db.migrations import m0012_care_dashboard_visibility
from db.migrations import m0013_timer_warning_ack
from db.migrations import m0014_volatility_and_interpolation_gap_cap
from db.migrations import m0015_tuya_cloud_credentials
from db.migrations import m0016_animal_species_profile
from db.migrations import m0017_care_nag_count
from db.migrations import m0018_plug_timer_controller_kind
from db.migrations import m0019_feeding_detail_and_shed_log
from db.migrations import m0020_feeding_detail_prey_state_dry
from db.migrations import m0021_event_log
from db.migrations import m0022_room_sort_order
from db.migrations import m0023_animal_enclosure_images
from db.migrations import m0024_species_profile_kb
from db.migrations import m0025_plug_timer_multi_cycle
from db.migrations import m0026_user_auth
from db.migrations import m0027_animal_sex

MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "action_tracking", m0001_action_tracking.migrate),
    (2, "plugin_architecture", m0002_plugin_architecture.migrate),
    (3, "target_schedule", m0003_target_schedule.migrate),
    (4, "animal_dashboard_visibility", m0004_animal_dashboard_visibility.migrate),
    (5, "plug_dashboard_visibility", m0005_plug_dashboard_visibility.migrate),
    (6, "sensor_dashboard_visibility", m0006_sensor_dashboard_visibility.migrate),
    (7, "sensor_reading_metrics", m0007_sensor_reading_metrics.migrate),
    (8, "plug_always_on", m0008_plug_always_on.migrate),
    (9, "salinity_specific_gravity", m0009_salinity_specific_gravity.migrate),
    (10, "plug_group", m0010_plug_group.migrate),
    (11, "uvb_index", m0011_uvb_index.migrate),
    (12, "care_dashboard_visibility", m0012_care_dashboard_visibility.migrate),
    (13, "timer_warning_ack", m0013_timer_warning_ack.migrate),
    (14, "volatility_and_interpolation_gap_cap", m0014_volatility_and_interpolation_gap_cap.migrate),
    (15, "tuya_cloud_credentials", m0015_tuya_cloud_credentials.migrate),
    (16, "animal_species_profile", m0016_animal_species_profile.migrate),
    (17, "care_nag_count", m0017_care_nag_count.migrate),
    (18, "plug_timer_controller_kind", m0018_plug_timer_controller_kind.migrate),
    (19, "feeding_detail_and_shed_log", m0019_feeding_detail_and_shed_log.migrate),
    (20, "feeding_detail_prey_state_dry", m0020_feeding_detail_prey_state_dry.migrate),
    (21, "event_log", m0021_event_log.migrate),
    (22, "room_sort_order", m0022_room_sort_order.migrate),
    (23, "animal_enclosure_images", m0023_animal_enclosure_images.migrate),
    (24, "species_profile_kb", m0024_species_profile_kb.migrate),
    (25, "plug_timer_multi_cycle", m0025_plug_timer_multi_cycle.migrate),
    (26, "user_auth", m0026_user_auth.migrate),
    (27, "animal_sex", m0027_animal_sex.migrate),
]

LATEST_VERSION = MIGRATIONS[-1][0]

assert [v for v, _, _ in MIGRATIONS] == list(range(1, LATEST_VERSION + 1)), "migration numbers must be 1..N with no gaps"
