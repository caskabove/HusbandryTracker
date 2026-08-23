"""Probe a single Tuya (Gosund) plug's raw DPS status repeatedly.

Use this after running `python -m tinytuya wizard` (which logs into the Tuya IoT platform and
prints device_id/local_key/ip for every plug on your account) to confirm which DPS key is the
actual on/off switch before registering the plug. DPS key "1" is the on/off switch for most
single-outlet Tuya plugs, but it's not guaranteed for every model — toggle the plug from the
Google Home app while this is running and watch which key flips.

Usage:
    python tools/tuya_probe.py <device_id> <local_key> [--ip IP] [--version 3.3]
"""
from __future__ import annotations

import argparse
import time

import tinytuya


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("device_id")
    parser.add_argument("local_key")
    parser.add_argument("--ip", default="Auto", help="LAN IP; 'Auto' lets tinytuya discover it (slower)")
    parser.add_argument("--version", default="3.3")
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()

    device = tinytuya.OutletDevice(args.device_id, args.ip, args.local_key, version=args.version)

    print("Polling raw DPS status. Toggle the plug from the Google Home app and watch which key flips. Ctrl+C to stop.\n")
    try:
        while True:
            status = device.status()
            print(status.get("dps", status))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
