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
- **Python** — free software that runs the website and the background listeners. [Download it here](https://www.python.org/downloads/)
  (get the latest version) and install it. During installation, make sure to check the box that
  says **"Add python.exe to PATH"** — that's the one setting that matters.
- **Your Govee sensors** (the **H5074** or **H5102** models — HerpMonitor understands both), one
  or more per enclosure, already set up and working in the Govee Home phone app.
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

The first time, run the one-time setup step below; after that, just double-click the **HerpMonitor**
shortcut on your Desktop.

```
python tray\install.py
```

This creates a **HerpMonitor** shortcut on your Desktop. Double-clicking it starts the website,
Ingest, and both plugins in the background (no windows to manage) and opens the dashboard in your
browser after a few seconds. You'll see a small icon appear in the system tray (bottom-right, near
the clock) — right-click it for a menu that lets you Open Dashboard, Start/Stop/Restart each part
individually, View Logs, or tick **"Start with Windows"** so HerpMonitor comes up automatically
every time you log in, the same way apps like Docker Desktop or Steam do. The icon turns yellow if
something's restarting and red if something's failed repeatedly and needs your attention.

**Don't see the shortcut after running that command?** See "The Desktop shortcut didn't appear" in
Section 7 below — it's almost always your Desktop folder being in a different location than usual,
not a real error.

### The manual way

Useful if you want to see what's actually happening without going through the tray icon. Every time
you want to use HerpMonitor, you start **four things**, each in its own Command Prompt window:

**Website:**
```
.venv\Scripts\activate
python -u -m uvicorn web.main:app --host 127.0.0.1 --port 22255
```

**Ingest** (open a second Command Prompt window for this one):
```
.venv\Scripts\activate
python -u ingest\ingest.py
```

**Sensor plugin** (open a third Command Prompt window for this one):
```
.venv\Scripts\activate
python -u plugins\govee_ble\plugin.py
```

**Plug plugin** (open a fourth Command Prompt window for this one):
```
.venv\Scripts\activate
python -u plugins\tuya_lan\plugin.py
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

### Getting notified when something's wrong (Send Alert)

Besides coloring things red on the dashboard, HerpMonitor can push a notification straight to your
phone when a Sensor reading goes out of range, a heat/cooling Plug is switched on but not actually
drawing power (a burnt-out bulb or failed element), or a Smart Sensor/Plug stops reporting
altogether. This only checks Smart Sensors/Plugs with Auto-Update on (see below) — Manual ones have
nothing automatic to watch.

It only fires after a problem has stuck around for a while (10 minutes by default, not the instant
it's first noticed) — a single noisy reading or a momentary network blip won't wake you up for
nothing. You'll also get a second notification once things are back to normal, so you know both
when something broke and when it got fixed.

**Setting it up** uses **[ntfy](https://ntfy.sh)**, a free, no-account-needed push notification
app:

1. Install the **ntfy** app on your phone (search your phone's app store) — or use
   [ntfy.sh](https://ntfy.sh) in a browser if you'd rather.
2. In the app, **subscribe to a topic** — pick any name nobody else is likely to guess (it's not
   password-protected, so something like `herpmonitor-yourname-4821` is safer than plain
   `herpmonitor`). This is like a private radio channel: whoever subscribes to the same topic name
   gets the same notifications.
3. On HerpMonitor's main Admin page, in the **Settings** card, enter:
   - **ntfy Server URL**: `https://ntfy.sh` (unless you're self-hosting your own ntfy server)
   - **ntfy Topic**: the exact topic name you subscribed to
   - **Alert Debounce (minutes)**: how long a problem has to persist before you're notified
     (default 10)
4. Click **Save**.

Leave the ntfy fields blank to turn notifications off entirely — HerpMonitor still tracks whether
things are OK internally, it just won't push anything to your phone.

One current gap, so it's not a surprise: the "Plug switched on but not drawing power" check needs
Data Capture (wattage readings) to compare against, and none of the currently-supported Gosund plug
models report that — see the note under [Adding a plug](#adding-a-plug) below. Out-of-range Sensor
readings and unreachable-device notifications both work today regardless.

### Logging that you fed, watered, or cleaned an enclosure

Each enclosure's Admin page has a **Care** card at the top. Click **Today**, **Yesterday**, or **2
days ago** next to Feeding, Watering, Spot-clean, or Deep-clean — whichever it actually was. For
anything further back, click **Advanced** to get the full date/time picker.

**Feeding just one animal (spot-feeding)**: if an enclosure holds more than one animal (a community
tank, a pair), the Feeding row also shows a dropdown of that enclosure's animals, next to "Whole
enclosure." Pick a specific animal before clicking Today/Yesterday/2 days ago/Log — e.g. dropping an
extra pellet for one underweight fish in a community tank, without logging it as feeding the whole
tank. Leave it on "Whole enclosure" (the default) for the ordinary case of feeding everyone at once.
Watering, Spot-clean, and Deep-clean don't have this option — those always apply to the whole
enclosure.

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
- **Enclosure Type** — **Basic** (snake/lizard/tortoise/insect — the default), **Freshwater**,
  **Saltwater**, or **Amphibian**. This decides which Target Range fields show up later when you
  add a Sensor to this enclosure (see [Adding a sensor to an
  enclosure](#adding-a-sensor-to-an-enclosure) below) — Basic only ever needs
  temperature/humidity, Freshwater/Saltwater/Amphibian add water-chemistry fields instead (pH,
  ammonia, nitrite, nitrate, and — Saltwater only — specific gravity (e.g. 1.026), salinity in ppm
  (e.g. 35), alkalinity, calcium, magnesium, phosphate). You can change this later from Enclosure
  Settings if you got it wrong; it just
  changes which fields show, nothing already saved is erased.
- **Bioactive** — check this box if it has a live cleanup crew (isopods, springtails, live plants).
  Besides relaxing how often a Deep-clean is expected, this also unlocks a **Plants** card on the
  enclosure's page — see [Tracking Plants in a Bioactive
  enclosure](#tracking-plants-in-a-bioactive-enclosure) below.
- **Feeding / Watering / Spot-clean / Deep-clean interval** — how many days between each, for that
  enclosure. This is what drives the green/yellow/red colors, so set it to match how you actually
  care for that animal (a snake might be fed weekly; a small gecko might need feeding every 2-3
  days).

Click **Create**, and it takes you to that enclosure's own page.

### Adding an animal to an enclosure

On that enclosure's page, fill out the **"Add Animal"** form: name, common species name,
scientific name (optional), and date of birth (exact date, or just a year-month like `2024-05` if
you don't know the exact day).

### Tracking Plants in a Bioactive enclosure

Once an enclosure is checked **Bioactive**, its Admin page grows a **Plants** card. This is
entirely optional — you can log Plant Health for the enclosure as a whole without ever naming an
individual plant, or track specific ones by name, whichever fits how closely you watch them.

- **Adding a Plant**: fill out **"+ Add Plant"** — a name (e.g. "pothos", "left-side moss") and
  optionally a species. Each one gets a **remove** link once added.
- **Logging Plant Health**: the same card has a **Plant Health log** further down — pick a specific
  Plant from the dropdown (or leave it on "(whole enclosure)"), type what you observed (e.g.
  "pothos yellowing, moved out of direct light"), and click **Log**. There's a date/time box if
  you're logging something you noticed earlier. The 10 most recent entries show in the table above
  the form.

An enclosure with Bioactive unchecked has no Plants card at all — check that box first (Enclosure
Settings, at the top of the enclosure's page) if you don't see it.

### Adding a sensor to an enclosure

Every Sensor is either **Smart** (a real Govee device, read automatically) or **Manual** (no
device — you log readings by hand). Pick which one in the **"Add Sensor"** form's Tracking Mode
dropdown; it shows only the fields that mode actually needs. Which Target Range fields show up
below that depends on the enclosure's **Enclosure Type** (see [Adding a new
enclosure](#adding-a-new-enclosure) above) — a Basic enclosure only offers temperature/humidity; a
Freshwater/Saltwater/Amphibian one adds the water-chemistry fields for that type instead.

**How many, and where**: an Enclosure can have more than one Sensor — a common setup is one on the
warm side and one on the cool side, so each gets its own label and (if you want) its own target
range. Each Sensor belongs to exactly one Enclosure (or one Room, if it's a Room's ambient sensor —
see [Adding a Room](#adding-a-room-and-grouping-enclosures-into-it) below) — a device can't be shared
between two places the way a Plug can.

#### Smart Sensor (Govee)

This is the one step that needs a short detour into a Command Prompt, because finding a Govee
sensor's ID isn't something the website can do on its own yet.

1. Pair the sensor in the **Govee Home** app first, if you haven't already (one-time, unrelated to
   HerpMonitor — see [How To: Add a Govee Sensor](HOWTO_ADD_GOVEE_SENSOR.md) if you need the full
   walkthrough).
2. Open a Command Prompt in the HerpMonitor folder, and run:
   ```
   .venv\Scripts\activate
   python tools\govee_discover.py 20
   ```
3. Wait 20 seconds. It'll print a list of nearby Govee sensors, each with a code like
   `E3:60:59:23:50:A6` — that's the sensor's ID (its "MAC address").
4. To figure out *which* sensor belongs to *which* enclosure: check the current reading it prints
   against what the Govee Home app (or the sensor's own little screen) shows for that enclosure —
   they should match.
5. On the Admin page, in that enclosure's **"Add Sensor"** form (Tracking Mode: Smart), paste in
   that ID, give it a label (e.g. "warm side"), and optionally set a target temperature/humidity
   range — that's what turns the Temp/Humidity numbers green or red on the dashboard.
6. Click **Create**.

See [How To: Add a Govee Sensor](HOWTO_ADD_GOVEE_SENSOR.md) for this same walkthrough as a
standalone, start-to-finish doc.

#### Manual Sensor

For a spot-check tool with no BLE of its own (an infrared thermometer, a moisture meter, a water
test strip):

1. In the **"Add Sensor"** form, set **Tracking Mode** to **Manual**.
2. Give it a label.
3. Set a target range (**min *and* max**) on whichever it measures — this is required for a Manual
   Sensor, since there'd otherwise be nothing to judge a hand-logged reading against.
4. Click **Create**. Its dashboard row now grows a small "Log Reading" form you use whenever you
   take a measurement.

One current limitation, so it's not a surprise: the "Log Reading" form only ever logs temperature
and/or humidity. If you set a target range on one of the water-chemistry fields (pH, ammonia, etc.
— only offered on a Freshwater/Saltwater/Amphibian enclosure), it's saved and shown, but there's
nowhere yet to log an actual reading against it, so it won't get colored green/yellow/red like
temperature and humidity do. Setting it up now is still fine if you're testing water chemistry by
hand — the range itself is saved and ready for whenever reading-logging catches up to it.

**Have a Tuya/Smart-Life temperature/humidity sensor (with or without a probe), not a Govee
device?** That's a different product than what's covered above, and isn't read automatically yet —
if it's a Zigbee device (check the box for "Zigbee" and "Gateway required" — most of these small
screen/probe sensors are), see [How To: Add a Tuya Zigbee Temp/Humidity/Probe
Sensor](HOWTO_TUYA_TEMP_HUMIDITY_PROBE_SENSOR.md) for exactly what works today, **including a
required-hardware heads-up before you even open the box** (short version: it works great in the
Tuya Smart app on its own, but needs a separate gateway/hub to do so; inside HerpMonitor it's a
Manual Sensor for now).

### Adding a plug

Unlike Animals/Sensors (added from the Enclosure or Room they belong to), Plugs are added from the
**main Admin page** (`/admin`) — its own **"Plugs"** card, since a Plug can belong to more than one
place. Every Plug is either **Smart** (a real Tuya-controlled Gosund plug, read automatically) or
**Manual** (no smart device — e.g. a light on a mechanical timer); pick which one in the **"Add
Plug"** form's Tracking Mode dropdown, which shows only the fields that mode actually needs.

**How many, and where** — the **"Belongs to"** dropdown on that form is where you say what a single
physical Plug controls, and it's the one place a device can genuinely serve more than one thing:
- **Enclosure(s)**: check the box next to each Enclosure it serves. Almost always just one; check
  more than one when a single physical switch controls several tubs at once ("everything on one
  switch," common in smaller collections) — one Plug, several Enclosures, same on/off state for
  all of them since it really is the same physical device.
- **Room**: for a genuinely room-wide fixture (a rack's ambient light) that isn't tied to any
  specific tub — pick the Room instead of any Enclosure.

A Plug always belongs to exactly one of those, never both, never neither. Separately, a
**multi-outlet power strip** counts as *multiple* Plug rows sharing the same device ID/local key,
one per outlet actually in use — see Outlet/DPS key below.

#### Smart Plug (Gosund)

This is for tracking a Gosund plug's light/heat/cooling status (see the note at the end of this
guide for why this needs Smart Life instead of Google Home).

1. Pair the plug in the **Smart Life** app first, if you haven't already (see [How To: Add a Gosund
   Smart Plug](HOWTO_ADD_GOSUND_PLUG.md) for the full walkthrough) — **not** Google Home.
2. Get the plug's **device ID** and **local key**. Unlike a sensor's MAC address, these can't be
   found with a simple scan — getting them involves a one-time setup on Tuya's developer website
   (the company behind Gosund's underlying technology). **That part still needs technical help to
   walk through the first time** — see the linked how-to above for the actual commands involved.
3. On the main Admin page's **"Add Plug"** form, set **Tracking Mode** to **Smart**, give it a label
   (e.g. "UTH", "basking bulb"), and pick a **Purpose** (light/heat/cooling/etc.).
4. Enter the **device ID** and **local key** from step 2.
5. Leave **Outlet / DPS key** as `1` unless the plug is a multi-outlet power strip — those expose
   each outlet as its own switch (`1`, `2`, `3`, or `7` for a USB port), so a strip needs one row
   here per outlet actually in use, all sharing the same device ID/local key. `tools\tuya_probe.py`
   (a Command Prompt tool) can confirm which number is which outlet if you're not sure.
6. Leave the IP address blank unless a plug keeps failing to connect, in which case pinning its IP
   address can help.
7. Set **Belongs to** (see above), and click **Create**.

See [How To: Add a Gosund Smart Plug](HOWTO_ADD_GOSUND_PLUG.md) for this same walkthrough as a
standalone, start-to-finish doc, including the Tuya developer-credentials step in full.

#### Manual Plug

For a light/heat source switched by hand or by a plain mechanical timer with no smart features:

1. In the **"Add Plug"** form, set **Tracking Mode** to **Manual**.
2. Give it a label and a **Purpose**.
3. Enter the timer's on-time and off-time. No device ID or local key needed.
4. Set **Belongs to** (see above), and click **Create**.

The dashboard shows that as a "Declared" schedule — it's exactly what you entered, not something the
app is verifying against the timer.

**Reassigning a plug already sitting in "Unassigned"**: open its edit page from the Plugs list on
the main Admin page, check the box(es) for its real Enclosure(s) (or switch "Belongs to" over to
Room), fix the label/Purpose, and save — no need to re-enter the device ID or local key, those stay
attached to the physical plug. A Plug lands back in Unassigned on its own if it ever loses its last
Enclosure (e.g. that Enclosure gets deleted) — it's a safety net, not something you manage directly.

**Data Capture** — as of this version, a Smart Plug's edit page doesn't show any wattage/power
reading, even though the database has a place for one. That's not a bug: none of Gosund's actual
plug models report power draw over the local connection this app uses, only on/off state and a
countdown timer, so there's currently nothing to show. This is already wired up and ready — the
moment a plug that *does* report wattage gets added, it'll start capturing automatically, no setup
needed.

### Pausing a Sensor or Plug without removing it (Auto-Update)

Every Smart Sensor or Smart Plug's edit page has an **Auto-Update** checkbox, checked by default.
Uncheck it to pause that device's background collection — no more Readings, on/off tracking, or
Send Alert checks for it — without losing its setup (MAC address, device ID, local key, target
ranges, everything). Check it again any time to resume.

Use this for a device that's temporarily not telling you anything useful: a sensor pulled out for
cleaning, a plug unplugged for the season, or one that's gone flaky and keeps triggering Send Alert
notifications you don't need right now. It's not the same as switching Tracking Mode to Manual —
that's for permanently swapping the physical hardware; Auto-Update is for a temporary pause on the
same device.

One thing to know: pausing a Sensor or a Plug both take effect within a few seconds — the next time
its plugin polls or hears from it, it checks whether you've paused it first.

### Removing something

Every animal and sensor has a small **"remove"** link next to it, and a Plug has a **"Delete
Plug"** button on its own edit page. There's also a **"Delete Enclosure"** button on the
enclosure's page (and a matching one for a Room), which removes everything that belongs
*exclusively* to it — it asks you to confirm first, since that can't be undone. A Plug shared with
other Enclosures just loses that one link and keeps going; see "Reassigning" above for what happens
if it loses its last one.

---

## 6. Stopping HerpMonitor

Right-click the tray icon and choose **Stop All**, or **Quit** to also close the tray icon itself.
(Quit is what you want before updating the software; Stop All leaves the tray icon running so you
can Start All again from the same menu later.)

You don't strictly need to stop anything — it's fine to leave it running all the time (that's
actually the normal way to use it, so history keeps accumulating, and "Start with Windows" assumes
you will). Stopping is only needed if you're restarting the computer, updating the software, or
troubleshooting.

---

## 7. If Something's Not Working

- **The website won't load at `localhost:22255`, or Temp/Humidity is stuck on "no data yet"** —
  Right-click the tray icon and check for a red (failed) or yellow (restarting) status; click
  **Start** on whichever part shows it, or **View Logs** to see why it's been crashing. If the tray
  icon itself isn't there at all, double-click the HerpMonitor Desktop shortcut again. Also double
  check Bluetooth is turned on (the sensor plugin needs it).
- **A reading looks obviously wrong** (like a huge negative number) — Let me know rather than
  trusting it; that's a sign the sensor decoding needs another look for that specific device.
- **The Desktop shortcut didn't appear after running `python tray\install.py`** — `install.py` asks
  Windows itself where your Desktop is and puts the shortcut there, so if nothing shows up, your
  Desktop folder is almost certainly somewhere other than the plain `C:\Users\<you>\Desktop` you'd
  expect — common with OneDrive's "back up your folders"/Known Folder Move feature, or if someone
  manually relocated it via a folder's Properties dialog. To check and fix:
  1. Open **File Explorer**, right-click **Desktop** in the left sidebar (under Quick Access or This
     PC), choose **Properties**, and open the **Location** tab. It'll show where Windows currently
     thinks your Desktop is — if that's not where you were looking, that's the mismatch.
  2. If you want it back to normal, click **Restore Default**, then **Apply**. Windows may say the
     default folder (`C:\Users\<you>\Desktop`) doesn't exist yet — that's expected if it's never
     been used before; let it create the folder.
  3. It'll then ask whether to move your existing files from the old location to the new one — say
     **Yes** only if those files are things you actually want as desktop icons, otherwise **No** (the
     restored Desktop just starts empty; the old files stay exactly where they were).
  4. **If OneDrive is running, it can hold a lock on the old folder and block the move** — if step 2
     or 3 fails or hangs, click the **^** (show hidden icons) arrow in the system tray, right-click
     the OneDrive cloud icon, open its gear/**Help & Settings** menu, choose **Close OneDrive**,
     confirm, then retry step 2. You can reopen OneDrive afterward from the Start menu if you use it
     for anything else.
  5. Once your Desktop is a real, existing folder, re-run `python tray\install.py` — the shortcut
     will land there.

---

## Note: Gosund plugs and the "no schedule data yet" message

Gosund plugs are tracked through **Smart Life**, not Google Home — Google Home has no way to hand
out the credentials this needs, so each plug had to be individually reset and re-added in Smart
Life first (already done for all your plugs). Newly-added plugs sit in an **"Unassigned"**
enclosure in Admin until you tell it which real enclosure and purpose (light/heat/cooling) each
one is — see [Adding a plug](#adding-a-plug) above for the reassignment steps.

Even once a plug is properly assigned, the "Schedules" section will still say "no schedule data
yet" for a while — HerpMonitor figures out a plug's on-time/duration by *watching* it over time,
not by reading a schedule directly, so it needs to see at least one full on/off cycle first.
