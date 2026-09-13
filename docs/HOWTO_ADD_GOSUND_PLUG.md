# How To: Add a Gosund Smart Plug

This covers Gosund WiFi smart plugs — the kind you plug a heat mat, basking bulb, fan, or light
into so HerpMonitor can see whether it's on or off, automatically. These plugs run on Tuya's
technology under the hood (same company behind the Tuya Smart app), but are set up through a
different, older app: **Smart Life**.

**Read this first:** unlike the Govee sensor or the Tuya Zigbee sensor, this device connects
directly to your home WiFi — no Bluetooth, no gateway/hub needed. But getting HerpMonitor talking
to it takes one extra, more technical step beyond just pairing it in the app (see [Get Tuya
Developer Credentials](#3-get-tuya-developer-credentials) below) — that part genuinely benefits
from an extra pair of hands the first time, so don't be surprised if it's the slow part.

**Contents**
1. [What You Need](#1-what-you-need)
2. [Add Tuya Device (Pairing the Plug in Smart Life)](#2-add-tuya-device-pairing-the-plug-in-smart-life)
3. [Get Tuya Developer Credentials](#3-get-tuya-developer-credentials)
4. [Confirming the On/Off Switch Key](#4-confirming-the-onoff-switch-key)
5. [Adding It to HerpMonitor](#5-adding-it-to-herpmonitor)
6. [Using It Day to Day](#6-using-it-day-to-day)

---

## 1. What You Need

- **The Gosund plug itself**, plugged into power.
- **The Smart Life app** on your phone — free, from your phone's app store (search "Smart Life").
  **Not Google Home** — Google Home has no way to hand HerpMonitor the credentials it needs, even
  though it can also control the same plug. Gosund plugs must be set up in Smart Life (or Tuya
  Smart — either works for this step) for the rest of this guide to work.
- **Your phone connected to 2.4GHz WiFi during pairing** — most inexpensive smart plugs, this one
  included, can only join a 2.4GHz network, not 5GHz. If your router broadcasts both under the same
  name, this is the most common reason pairing silently fails — see the same callout in the [Tuya
  Zigbee sensor how-to](HOWTO_TUYA_TEMP_HUMIDITY_PROBE_SENSOR.md#1-what-you-need) for how to check.
- **The HerpMonitor folder set up already** (section 2 of `docs/USER_GUIDE.md`) — step 3 below runs
  a command from inside it.

---

## 2. Add Tuya Device (Pairing the Plug in Smart Life)

1. Open the **Smart Life** app and create a free account if you haven't already.
2. Tap **Add Device**. Scroll down through the categories/device list and select the plug (often
   listed under "Electrical" → "Socket," or it may auto-detect nearby).
3. Follow the on-screen pairing steps — this is where your phone's 2.4GHz WiFi connection matters
   (see the callout above); you'll be asked for your WiFi password so the plug itself can join your
   network directly.
4. Give it a name in the app — this is just for your own reference in Smart Life, separate from
   whatever label you give it in HerpMonitor later.
5. Confirm you can turn it on/off from the app before moving on.

*(If any of these exact screens or button names don't match what you actually see, let me know — this
section is written from how Tuya's standard pairing flow normally works, not a verified run-through,
and I'd rather fix it than leave it wrong.)*

---

## 3. Get Tuya Developer Credentials

Every Gosund plug has a **device ID** and **local key** — think of them like a name and password
HerpMonitor needs to talk to the plug directly over your WiFi, without going through Tuya's cloud
every time. Unlike a Govee sensor's ID, these can't be found with a simple scan; getting them
requires linking a free Tuya developer account to the same account you just used in Smart Life. This
is the one part of setup that's genuinely more technical — plan on doing it once with someone
comfortable following a multi-step wizard, not per-plug.

1. Open a Command Prompt in the HerpMonitor folder, and run:
   ```
   .venv\Scripts\activate
   python -m tinytuya wizard
   ```
2. This walks you through, step by step, in the same window:
   - Creating a free account at Tuya's IoT developer platform (a website, separate from Smart Life),
     if you don't already have one.
   - Creating a "Cloud" project there and linking it to your Smart Life account — this step usually
     involves scanning a QR code with your phone (in the Smart Life app) to prove it's really your
     account.
   - Typing in a couple of values the website shows you (an Access ID and Access Secret) back into
     the Command Prompt window.
3. Once finished, it prints (and saves into `devices.json`/`snapshot.json` in that same folder) every
   linked plug's **device ID**, **local key**, and last-known **IP address** on your network.

**This step's website screens belong to Tuya, not HerpMonitor** — their exact wording/layout can
change over time and isn't something this guide can promise pixel-for-pixel. If you get stuck partway
through the wizard, tell me exactly what screen/prompt you're on and I'll help from there.

`devices.json`/`snapshot.json` contain real credentials — they're already set up to be ignored by
git (never uploaded/shared), but don't email or paste them anywhere either.

---

## 4. Confirming the On/Off Switch Key

Most single-outlet plugs use the same internal switch key ("1"), but it's not guaranteed for every
model — worth a quick check before registering it in HerpMonitor:

```
python tools\tuya_probe.py <device_id> <local_key> --ip <ip_from_wizard>
```

While this is running, toggle the plug from the Smart Life app and confirm which key flips in the
output. If it's not `1`, you'll enter that number instead in the next step.

Leave the IP address blank later in HerpMonitor unless a plug keeps failing to connect — pinning its
IP (from the wizard's output) can help.

---

## 5. Adding It to HerpMonitor

Unlike Sensors (added from the Enclosure/Room they belong to), Plugs are added from HerpMonitor's
**main Admin page** (`/admin`), in its own **"Plugs"** card.

1. Fill out the **"Add Plug"** form: **Tracking Mode: Smart**, a label (e.g. "UTH", "basking bulb"),
   and a **Purpose** (heat/light/cooling/etc.).
2. **Belongs to**: check the Enclosure(s) it serves (almost always just one — check more than one
   only if a single physical plug controls several tubs at once), or pick a Room instead for a
   genuinely room-wide fixture.
3. Enter the **device ID** and **local key** from step 3 above.
4. Leave **Outlet/DPS key** as `1` unless step 4 above found a different number, or the plug is a
   multi-outlet power strip (which needs one row here per outlet actually in use — `2`, `3`, or `7`
   for a USB port — all sharing the same device ID/local key).
5. Click **Create**.

---

## 6. Using It Day to Day

Nothing to do — HerpMonitor polls this plug directly over your WiFi every few seconds and updates
its on/off status automatically, no app needed. The **Command** buttons on its pill (dashboard,
Room, or Enclosure page) let you turn it on/off manually right from HerpMonitor — useful for reacting
quickly to an alert. The **Schedules** card shows its inferred on-time once HerpMonitor has watched
it through at least one full on/off cycle; until then it'll say "no schedule data yet," which is
expected, not an error.
