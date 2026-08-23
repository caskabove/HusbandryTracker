"""Manual Device Registration CLI — stand-in for the admin screen until the Phase 2 web app exists.

Writes directly to the same SQLite DB the collectors and (later) the web app use, so anything
registered here carries forward with no re-entry needed. See CONTEXT.md: Device Registration.

Examples:
    python tools/register_device.py enclosure-add "Ball Python Tub" --bioactive
    python tools/register_device.py animal-add "Ball Python Tub" "Noodle" --common "Ball Python" --scientific "Python regius" --dob 2019-04-02
    python tools/register_device.py sensor-add "Ball Python Tub" "warm side" AA:BB:CC:DD:EE:FF --temp-min 26 --temp-max 32
    python tools/register_device.py plug-add "Ball Python Tub" "UTH" heat abc123deviceid 0123456789abcdef --ip 192.168.1.50
    python tools/register_device.py list
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.db import get_connection, init_db


def _enclosure_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM enclosure WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise SystemExit(f"No enclosure named {name!r}. Run enclosure-add first.")
    return row["id"]


def enclosure_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    conn.execute(
        """INSERT INTO enclosure (name, bioactive, feeding_interval_days, watering_interval_days,
                                   spot_clean_interval_days, deep_clean_interval_days)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            args.name,
            int(args.bioactive),
            args.feeding_interval,
            args.watering_interval,
            args.spot_clean_interval,
            args.deep_clean_interval,
        ),
    )
    print(f"Registered enclosure {args.name!r}")


def enclosure_update(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    enclosure_id = _enclosure_id(conn, args.name)
    fields = {
        "bioactive": None if args.bioactive is None else int(args.bioactive),
        "feeding_interval_days": args.feeding_interval,
        "watering_interval_days": args.watering_interval,
        "spot_clean_interval_days": args.spot_clean_interval,
        "deep_clean_interval_days": args.deep_clean_interval,
    }
    updates = {k: v for k, v in fields.items() if v is not None}
    if not updates:
        print("Nothing to update — pass at least one of --bioactive/--no-bioactive or an --*-interval flag")
        return
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    conn.execute(f"UPDATE enclosure SET {set_clause} WHERE id = ?", (*updates.values(), enclosure_id))
    print(f"Updated {args.name!r}: {updates}")


def animal_update(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    enclosure_id = _enclosure_id(conn, args.enclosure)
    row = conn.execute(
        "SELECT id FROM animal WHERE enclosure_id = ? AND name = ?", (enclosure_id, args.name)
    ).fetchone()
    if row is None:
        raise SystemExit(f"No animal named {args.name!r} in {args.enclosure!r}.")
    fields = {"species_common": args.common, "species_scientific": args.scientific, "dob": args.dob}
    updates = {k: v for k, v in fields.items() if v is not None}
    if not updates:
        print("Nothing to update — pass at least one of --common/--scientific/--dob")
        return
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    conn.execute(f"UPDATE animal SET {set_clause} WHERE id = ?", (*updates.values(), row["id"]))
    print(f"Updated {args.name!r} in {args.enclosure!r}: {updates}")


def animal_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    enclosure_id = _enclosure_id(conn, args.enclosure)
    conn.execute(
        "INSERT INTO animal (enclosure_id, name, species_common, species_scientific, dob) VALUES (?, ?, ?, ?, ?)",
        (enclosure_id, args.name, args.common, args.scientific, args.dob),
    )
    print(f"Registered animal {args.name!r} in {args.enclosure!r}")


def sensor_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    enclosure_id = _enclosure_id(conn, args.enclosure)
    conn.execute(
        """INSERT INTO sensor (enclosure_id, label, mac_address, target_temp_min_c, target_temp_max_c,
                                target_humidity_min, target_humidity_max)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (enclosure_id, args.label, args.mac.upper(), args.temp_min, args.temp_max, args.humidity_min, args.humidity_max),
    )
    print(f"Registered sensor {args.mac!r} ({args.label}) in {args.enclosure!r}")


def plug_add(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    enclosure_id = _enclosure_id(conn, args.enclosure)
    conn.execute(
        """INSERT INTO plug (enclosure_id, label, purpose, tuya_device_id, tuya_local_key, tuya_ip_address, switch_dps_key)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (enclosure_id, args.label, args.purpose, args.device_id, args.local_key, args.ip, args.dps_key),
    )
    print(f"Registered plug {args.device_id!r} dps={args.dps_key} ({args.purpose}: {args.label}) in {args.enclosure!r}")


def list_all(conn: sqlite3.Connection, _args: argparse.Namespace) -> None:
    for enclosure in conn.execute("SELECT * FROM enclosure ORDER BY name"):
        print(f"\n[{enclosure['name']}] bioactive={bool(enclosure['bioactive'])} "
              f"feed/{enclosure['feeding_interval_days']}d water/{enclosure['watering_interval_days']}d "
              f"spot/{enclosure['spot_clean_interval_days']}d deep/{enclosure['deep_clean_interval_days']}d")
        for animal in conn.execute("SELECT * FROM animal WHERE enclosure_id = ?", (enclosure["id"],)):
            print(f"  animal: {animal['name']} ({animal['species_common']} / {animal['species_scientific']}) dob={animal['dob']}")
        for sensor in conn.execute("SELECT * FROM sensor WHERE enclosure_id = ?", (enclosure["id"],)):
            if sensor["tracking_mode"] == "manual":
                print(f"  sensor: {sensor['label']} (Manual — hand-logged readings)")
            else:
                print(f"  sensor: {sensor['label']} mac={sensor['mac_address']}")
        for plug in conn.execute("SELECT * FROM plug WHERE enclosure_id = ?", (enclosure["id"],)):
            if plug["tracking_mode"] == "manual":
                on, off = plug["declared_on_time"] or "?", plug["declared_off_time"] or "?"
                print(f"  plug:   {plug['label']} purpose={plug['purpose']} (Manual — declared {on}-{off})")
            else:
                print(f"  plug:   {plug['label']} purpose={plug['purpose']} device_id={plug['tuya_device_id']} dps={plug['switch_dps_key']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("enclosure-add", help="Register a new Enclosure")
    p.add_argument("name")
    p.add_argument("--bioactive", action="store_true")
    p.add_argument("--feeding-interval", type=int, default=7)
    p.add_argument("--watering-interval", type=int, default=3)
    p.add_argument("--spot-clean-interval", type=int, default=7)
    p.add_argument("--deep-clean-interval", type=int, default=30)
    p.set_defaults(func=enclosure_add)

    p = sub.add_parser("enclosure-update", help="Update fields on an existing Enclosure")
    p.add_argument("name")
    p.add_argument("--bioactive", dest="bioactive", action="store_true", default=None)
    p.add_argument("--no-bioactive", dest="bioactive", action="store_false")
    p.add_argument("--feeding-interval", type=int, default=None)
    p.add_argument("--watering-interval", type=int, default=None)
    p.add_argument("--spot-clean-interval", type=int, default=None)
    p.add_argument("--deep-clean-interval", type=int, default=None)
    p.set_defaults(func=enclosure_update)

    p = sub.add_parser("animal-add", help="Register an Animal in an existing Enclosure")
    p.add_argument("enclosure")
    p.add_argument("name")
    p.add_argument("--common", dest="common", default=None, help="Common species name")
    p.add_argument("--scientific", dest="scientific", default=None, help="Latin/scientific species name")
    p.add_argument("--dob", default=None, help="ISO date, e.g. 2019-04-02")
    p.set_defaults(func=animal_add)

    p = sub.add_parser("animal-update", help="Update fields on an existing Animal")
    p.add_argument("enclosure")
    p.add_argument("name")
    p.add_argument("--common", dest="common", default=None)
    p.add_argument("--scientific", dest="scientific", default=None)
    p.add_argument("--dob", default=None)
    p.set_defaults(func=animal_update)

    p = sub.add_parser("sensor-add", help="Register a Govee Sensor's MAC against an Enclosure")
    p.add_argument("enclosure")
    p.add_argument("label", help='e.g. "warm side", "cool side"')
    p.add_argument("mac", help="Govee MAC address, from tools/govee_discover.py")
    p.add_argument("--temp-min", type=float, default=None, help="Target Range min, Celsius")
    p.add_argument("--temp-max", type=float, default=None, help="Target Range max, Celsius")
    p.add_argument("--humidity-min", type=float, default=None)
    p.add_argument("--humidity-max", type=float, default=None)
    p.set_defaults(func=sensor_add)

    p = sub.add_parser("plug-add", help="Register a Gosund Plug against an Enclosure")
    p.add_argument("enclosure")
    p.add_argument("label", help='e.g. "basking bulb", "UTH"')
    p.add_argument("purpose", choices=["light", "heat", "cooling"])
    p.add_argument("device_id", help="Tuya device_id, from the tinytuya wizard")
    p.add_argument("local_key", help="Tuya local_key, from the tinytuya wizard")
    p.add_argument("--ip", default=None, help="Optional: pin the plug's LAN IP instead of relying on discovery")
    p.add_argument("--dps-key", default="1", help='DPS switch key for this outlet (default "1"; power strips '
                                                    'use "2", "3", etc., or "7" for USB — see tools/tuya_probe.py)')
    p.set_defaults(func=plug_add)

    p = sub.add_parser("list", help="List everything registered")
    p.set_defaults(func=list_all)

    return parser


def main() -> None:
    init_db()
    parser = build_parser()
    args = parser.parse_args()
    with get_connection() as conn:
        args.func(conn, args)


if __name__ == "__main__":
    main()
