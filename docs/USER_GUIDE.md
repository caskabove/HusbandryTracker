# HerpMonitor — User Guide

HerpMonitor is a private website, running on your own computer, that keeps track of each
enclosure's temperature, humidity, and feeding/watering/cleaning history in one place — instead of
juggling a separate phone app and your own memory for each tank.

This guide explains what you need, how to set HerpMonitor up, how to start it, and how to use it
day to day. No technical background assumed — anywhere you need to type something, it's spelled
out exactly.

**Contents**
1. [What You Need](#1-what-you-need)
2. [One-Time Setup](#2-one-time-setup)
3. [Starting HerpMonitor](#3-starting-herpmonitor)
4. [Using the Dashboard](#4-using-the-dashboard)
5. [Using the Admin Page](#5-using-the-admin-page-addingediting-enclosures)
6. [Stopping HerpMonitor](#6-stopping-herpmonitor)
7. [If Something's Not Working](#7-if-somethings-not-working)

---

## 1. What You Need

- **A Windows computer that stays on, in the same room (or close to) your animals.** It needs to
  stay running and stay near your Govee sensors, because it listens for their signal over
  Bluetooth — the further away, the less reliable the readings.
- **Python** — free software that runs both the website and the sensor listener. [Download it here](https://www.python.org/downloads/)
  (get the latest version) and install it. During installation, make sure to check the box that
  says **"Add python.exe to PATH"** — that's the one setting that matters.
- **Your Govee H5074 sensors**, one per enclosure, already set up and working in the Govee phone
  app.
- **Bluetooth turned on** on the Windows computer.

Gosund smart plugs, for tracking light/heat/cooling — set up through the Smart Life app (not
Google Home; see the note at the end of this guide for why).

---

## 2. One-Time Setup

You only do this once, when first installing HerpMonitor on a computer.

1. Get the HerpMonitor project folder onto the computer (however you normally do that — copying
   the folder, or `git clone` if you're comfortable with that).
2. Open a **Command Prompt** (search "cmd" in the Start menu) and navigate into the folder. If the
   folder is at `C:\Users\YourName\HerpMonitor`, type:
   ```
   cd C:\Users\YourName\HerpMonitor
   ```
3. Set up Python's workspace (this only needs to happen once):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   You'll know it worked if you see a list of package names scroll by with no red error text at
   the end.

That's it for one-time setup. You won't need to repeat this unless you move HerpMonitor to a
different computer.

---

## 3. Starting HerpMonitor

### The easy way

Double-click **`start.bat`** in the HerpMonitor folder. It opens three windows (the website, the
sensor listener, and the plug listener) and automatically opens the dashboard in your browser
after a few seconds.

Leave all three windows open (minimized is fine) — closing one stops that part. You can close the
first little window that says "HerpMonitor is running" once it says so; the other three keep
going.

### The manual way

Useful if `start.bat` doesn't work for some reason, or you want to see what it's actually doing.
Every time you want to use HerpMonitor, you start **three things**, each in its own Command Prompt
window:

**Website:**
```
.venv\Scripts\activate
python -u -m uvicorn web.main:app --host 127.0.0.1 --port 22255
```

**Sensor listener** (open a second Command Prompt window for this one):
```
.venv\Scripts\activate
python -u collectors\govee_collector.py
```

**Plug listener** (open a third Command Prompt window for this one):
```
.venv\Scripts\activate
python -u collectors\tuya_collector.py
```

Then open a web browser to:
```
http://localhost:22255
```
This only works on the computer HerpMonitor is running on (that's intentional — it's a private,
local-only dashboard, not accessible from other devices or the internet).

---

## 4. Using the Dashboard

The dashboard is a glance-only screen, one panel per enclosure, nothing to fill out here except a
Manual Sensor's readings (see below). Panels are grouped by **Room** (see Section 5) — each Room
gets a heading showing its own ambient reading and Light Schedule, with its Enclosures' panels
underneath; any Enclosure not yet assigned to a Room lands in an "Ungrouped" section at the end.
Each panel shows:

- **Enclosure name**, and each animal living in it (name, species, date of birth), at the top —
  click it to jump to that enclosure's Admin page.
- **Temp / Humidity** — the latest reading from that enclosure's own sensor(s). If it has none of
  its own but belongs to a Room, it instead shows that Room's Fallback Sensor reading, labeled
  "room" and always gray — that reading is real, but it's the room's general condition, not a
  judgment on whether it's right for that specific animal.
- **Care** — how long it's been since the enclosure was last fed, watered, spot-cleaned, and
  deep-cleaned. Click any of those (e.g. "3d ago", "never") to jump straight to that specific log
  entry on the enclosure's Admin page.

Schedules (light/heat/cooling on-times) and the actual Care logging buttons live on each
enclosure's Admin page instead — see Section 5.

### Forcing a fresh reading with "↻ Refresh"

A Room or Enclosure with at least one Smart (Govee) Sensor of its own gets a small **"↻ Refresh"**
button next to its name. Clicking it waits for a real live reading from that Sensor right now,
instead of whatever the background listener last happened to hear — real sensors only broadcast
every 10-60+ seconds, so this can take a little while (the browser just waits; that's normal).
Only ever refreshes what that Room/Enclosure actually owns — a Room's button never reaches into its
Enclosures, and an Enclosure showing a Room's Fallback Sensor reading has no button of its own (use
the Room's instead). How long it waits before giving up is the **Refresh Timeout** setting on the
main Admin page (default 30s).

### What the colors mean

| Color | Meaning |
|---|---|
| 🟢 Green | All good — recently done / reading is in the target range |
| 🟡 Yellow | Getting close to due |
| 🔴 Red | Overdue / reading is outside the target range / never logged |
| ⚪ Gray | No data yet, or no target range has been set for that sensor |

### Logging a Manual Sensor's reading

A Manual Sensor (see below) has no physical device feeding it data, so it shows a small "Log
Reading" form right under its row on the dashboard — enter whatever value(s) you just measured and
click it. There's a date/time box if you're logging a reading from earlier rather than right now;
leave it blank to log it as now.

---

## 5. Using the Admin Page (adding/editing enclosures)

Click **"Admin"** in the top-right of the dashboard, or go to `http://localhost:22255/admin`.
This is where you set up enclosures, animals, sensors, and plugs — and it's also where Care Events
get logged and Schedules are shown (the dashboard is glance-only; clicking an enclosure name or a
Care entry there brings you straight here).

### Logging that you fed, watered, or cleaned an enclosure

Each enclosure's Admin page has a **Care** card at the top. Click **Today**, **Yesterday**, or **2
days ago** next to Feeding, Watering, Spot-clean, or Deep-clean — whichever it actually was. For
anything further back, click **Advanced** to get the full date/time picker.

### Checking a plug's schedule

Each enclosure's Admin page has a **Schedules** card near the bottom, one row per Plug. A Smart
Plug shows its inferred on-time once that feature is fully turned on (see note at the end); a
Manual Plug shows the on/off time you declared for it when adding the plug; a Plug with a
**Controller Kind** set (see below) shows its Target Temperature or Target Humidity instead — a
Schedule wouldn't mean anything for one of those.

### Marking a plug as Thermostat- or Hydrostat-Controlled

If a heat/cooling Plug actually powers a separate thermostat unit (a Herpstat, Vivarium
Electronics, Jump Start, etc.) rather than the heat source directly — or a humidity Plug powers a
separate humidity controller (a MistKing misting system's control unit, a humidistat-driven fogger)
rather than the moisture source directly — set its **Controller Kind** to **Thermostat-Controlled**
or **Hydrostat-Controlled** when adding or editing it, and enter the matching **Target Temperature**
or **Target Humidity** you've set that controller to. A Plug is at most one of the two — one
physical relay powers one downstream device. This works whether the Plug itself is Smart or Manual
— either way, the controller's actual on/off cycling happens downstream, invisible to HerpMonitor,
so showing a Schedule for it would be misleading; the Target value is the one thing that's actually
meaningful to record. This doesn't judge whether the enclosure is actually at that temperature/
humidity — that's still a real Sensor's Target Range, if you have one in there.

### Adding a Room, and grouping enclosures into it

A **Room** groups Enclosures that share a physical space (e.g. "Living Room"). It's optional — an
Enclosure with no Room behaves exactly as before. On the main Admin page, fill out the **"Add
Room"** form: just a name. Click into the new Room's page to add its own ambient Sensor(s) (Smart
or Manual, same as an Enclosure's) and its **Light Schedule** — an on-time/off-time for the room's
general lighting, plus a free-text note for anything else worth capturing (e.g. "natural light from
east window", "dimmed after 6pm").

To put an Enclosure in a Room, go to that Enclosure's own Admin page and pick it from the **Room**
dropdown in Enclosure Settings.

**Fallback Sensor**: if an Enclosure has no Sensor of its own but belongs to a Room, its Enclosure
Settings form grows a **Fallback Sensor** dropdown listing that Room's Sensor(s) — pick whichever
one sits physically closest to that Enclosure. The dashboard will then show that Sensor's reading
on the Enclosure's own panel (clearly labeled, always gray — see Section 4 for why). If the
Enclosure later gets a real Sensor of its own, that always takes priority and the Fallback Sensor
stops being used.

### Adding a new enclosure

On the Admin page, fill out the **"Add Enclosure"** form at the bottom:
- **Name** — whatever you call the tank (e.g. "Gargoyl", "The Cape")
- **Bioactive** — check this box if it has a live cleanup crew (isopods, springtails, live plants)
- **Feeding / Watering / Spot-clean / Deep-clean interval** — how many days between each, for that
  enclosure. This is what drives the green/yellow/red colors, so set it to match how you actually
  care for that animal (a snake might be fed weekly; a small gecko might need feeding every 2-3
  days).

Click **Create**, and it takes you to that enclosure's own page.

### Adding an animal to an enclosure

On that enclosure's page, fill out the **"Add Animal"** form: name, common species name,
scientific name (optional), and date of birth (exact date, or just a year-month like `2024-05` if
you don't know the exact day).

### Adding a sensor to an enclosure

Every Sensor is either **Smart** (a real Govee device, read automatically) or **Manual** (no
device — you log readings by hand). Pick which one in the **"Add Sensor"** form's Tracking Mode
dropdown; it shows only the fields that mode actually needs.

**Smart Sensor** — this is the one step that needs a short detour into a Command Prompt, because
finding a Govee sensor's ID isn't something the website can do on its own yet.

1. Open a Command Prompt in the HerpMonitor folder, and run:
   ```
   .venv\Scripts\activate
   python tools\govee_discover.py 20
   ```
2. Wait 20 seconds. It'll print a list of nearby Govee sensors, each with a code like
   `E3:60:59:23:50:A6` — that's the sensor's ID (its "MAC address").
3. To figure out *which* sensor belongs to *which* enclosure: check the current reading it prints
   against what the Govee app (or the sensor's own little screen) shows for that enclosure — they
   should match.
4. On the Admin page, in that enclosure's **"Add Sensor"** form (Tracking Mode: Smart), paste in
   that ID, give it a label (e.g. "warm side"), and optionally set a target temperature/humidity
   range — that's what turns the Temp/Humidity numbers green or red on the dashboard.

**Manual Sensor** — for a spot-check tool with no BLE of its own (an infrared thermometer, a
moisture meter): pick Tracking Mode: Manual, give it a label, and set a target range (min *and*
max) on whichever it measures — temperature, humidity, or both. That range is required for a
Manual Sensor, since there'd otherwise be nothing to judge a hand-logged reading against. Once
saved, its dashboard row grows a small "Log Reading" form you use whenever you take a measurement.

### Adding a plug

Unlike Animals/Sensors (added from the Enclosure or Room they belong to), Plugs are added from the
**main Admin page** (`/admin`) — its own **"Plugs"** card, since a Plug can belong to more than one
place. Every Plug is either **Smart** (a real Tuya-controlled Gosund plug, read automatically) or
**Manual** (no smart device — e.g. a light on a mechanical timer); pick which one in the **"Add
Plug"** form's Tracking Mode dropdown, which shows only the fields that mode actually needs.

**Belongs to** — the other dropdown on that form — is where you say what the Plug controls:
- **Enclosure(s)**: check the box next to each Enclosure it serves. Almost always just one; check
  more than one when a single physical switch controls several tubs at once ("everything on one
  switch," common in smaller collections) — one Plug, several Enclosures, same on/off state for
  all of them since it really is the same physical device.
- **Room**: for a genuinely room-wide fixture (a rack's ambient light) that isn't tied to any
  specific tub — pick the Room instead of any Enclosure.

A Plug always belongs to exactly one of those, never both, never neither.

**Smart Plug** — this is for tracking a Gosund plug's light/heat/cooling status (see the note at
the end of this guide for why this needs Smart Life instead of Google Home).

Unlike a sensor's MAC address, a plug's ID and "local key" can't be found with a simple scan —
getting them involves a one-time setup on Tuya's developer website (the company behind Gosund's
underlying technology). That part still needs technical help to walk through the first time. Once
you have a plug's **device ID** and **local key** in hand, adding it here is simple: a label (e.g.
"UTH", "basking bulb"), a Purpose (light/heat/cooling/etc.), and those two values.

Leave **Outlet / DPS key** as `1` unless the plug is a multi-outlet power strip — those expose
each outlet as its own switch (`1`, `2`, `3`, or `7` for a USB port), so a strip needs one row here
per outlet actually in use, all sharing the same device ID/local key. `tools\tuya_probe.py` (a
Command Prompt tool) can confirm which number is which outlet if you're not sure.

Leave the IP address blank unless a plug keeps failing to connect, in which case pinning its IP
address can help.

**Manual Plug** — for a light/heat source switched by hand or by a plain mechanical timer with no
smart features: pick Tracking Mode: Manual, give it a label and Purpose, and enter the timer's
on-time and off-time. No device ID or local key needed. The dashboard shows that as a "Declared"
schedule — it's exactly what you entered, not something the app is verifying against the timer.

**Reassigning a plug already sitting in "Unassigned"**: open its edit page from the Plugs list on
the main Admin page, check the box(es) for its real Enclosure(s) (or switch "Belongs to" over to
Room), fix the label/Purpose, and save — no need to re-enter the device ID or local key, those stay
attached to the physical plug. A Plug lands back in Unassigned on its own if it ever loses its last
Enclosure (e.g. that Enclosure gets deleted) — it's a safety net, not something you manage directly.

### Removing something

Every animal and sensor has a small **"remove"** link next to it, and a Plug has a **"Delete
Plug"** button on its own edit page. There's also a **"Delete Enclosure"** button on the
enclosure's page (and a matching one for a Room), which removes everything that belongs
*exclusively* to it — it asks you to confirm first, since that can't be undone. A Plug shared with
other Enclosures just loses that one link and keeps going; see "Reassigning" above for what happens
if it loses its last one.

---

## 6. Stopping HerpMonitor

Close the **"HerpMonitor - Website"**, **"HerpMonitor - Sensor Listener"**, and **"HerpMonitor -
Plug Listener"** windows (or click into each and press `Ctrl+C`).

You don't strictly need to stop either one — it's fine to leave both running all the time (that's
actually the normal way to use it, so history keeps accumulating). Stopping is only needed if
you're restarting the computer, updating the software, or troubleshooting.

---

## 7. If Something's Not Working

- **The website won't load at `localhost:22255`, or Temp/Humidity is stuck on "no data yet"** —
  One of the two windows isn't running anymore. Easiest fix: close whatever HerpMonitor windows
  are still open and double-click `start.bat` again. Also double check Bluetooth is turned on (the
  sensor listener needs it).
- **A reading looks obviously wrong** (like a huge negative number) — Let me know rather than
  trusting it; that's a sign the sensor decoding needs another look for that specific device.

---

## Note: Gosund plugs and the "no schedule data yet" message

Gosund plugs are tracked through **Smart Life**, not Google Home — Google Home has no way to hand
out the credentials this needs, so each plug had to be individually reset and re-added in Smart
Life first (already done for all your plugs). Newly-added plugs sit in an **"Unassigned"**
enclosure in Admin until you tell it which real enclosure and purpose (light/heat/cooling) each
one is — see [Adding a plug to an enclosure](#adding-a-plug-to-an-enclosure) above for the
reassignment steps.

Even once a plug is properly assigned, the "Schedules" section will still say "no schedule data
yet" for a while — HerpMonitor figures out a plug's on-time/duration by *watching* it over time,
not by reading a schedule directly, so it needs to see at least one full on/off cycle first.
