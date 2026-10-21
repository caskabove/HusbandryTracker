# Husbandry Tracker — User Guide

Husbandry Tracker is a private website, running on your own computer, that keeps track of each
enclosure's temperature, humidity, schedules, and feeding/watering/cleaning history in one place —
instead of juggling a separate phone app and your own memory for each tank.

This guide picks up right after you've installed Husbandry Tracker with `HusbandryTrackerSetup.exe`
and walks through everything you'll actually do with it: your first launch, setting up your first
enclosure (animals, sensors, plugs), and using it day to day. No technical background assumed —
anywhere you need to type or click something, it's spelled out exactly.

This same guide is always available inside the app itself — click **Guide** in the top navigation
bar from any page.

Building Husbandry Tracker from source instead of using the installer (for development, or a
non-Windows platform)? See [Appendix A](#appendix-a-running-from-source) at the end — everything
else in this guide applies equally either way.

**Contents**
1. [What You Need](#1-what-you-need)
2. [First Launch](#2-first-launch)
3. [The Dashboard at a Glance](#3-the-dashboard-at-a-glance)
4. [Setting Up Your First Enclosure](#4-setting-up-your-first-enclosure)
5. [Tracking an Animal's Growth and Condition](#5-tracking-an-animals-growth-and-condition)
6. [Bioactive Enclosures and Plants](#6-bioactive-enclosures-and-plants)
7. [Rooms, Light Schedules, and Fallback Sensors](#7-rooms-light-schedules-and-fallback-sensors)
8. [Grouping Outlets on a Power Strip (Plug Groups)](#8-grouping-outlets-on-a-power-strip-plug-groups)
9. [Viewing History: View Data and Graphs](#9-viewing-history-view-data-and-graphs)
10. [Getting Notified When Something's Wrong](#10-getting-notified-when-somethings-wrong)
11. [Pausing a Device Without Removing It](#11-pausing-a-device-without-removing-it)
12. [Removing Something](#12-removing-something)
13. [Stopping Husbandry Tracker](#13-stopping-husbandry-tracker)
14. [Backing Up and Restoring Your Data](#14-backing-up-and-restoring-your-data)
15. [If Something's Not Working](#15-if-somethings-not-working)
- [Appendix A: Running From Source](#appendix-a-running-from-source)

---

## 1. What You Need

- **A Windows computer that stays on, in the same room (or close to) your animals.** It needs to
  stay running and stay near your Govee sensors, because it listens for their signal over
  Bluetooth — the further away, the less reliable the readings.
- **Bluetooth turned on** on that computer.
- **Govee sensors** (the **H5074** or **H5102** models — Husbandry Tracker understands both), one or
  more per enclosure, already set up and working in the Govee Home phone app.
- Optionally, **Gosund smart plugs** (for your lights, heat, and cooling), set up through the
  **Smart Life** app (not Google Home — see [Section 4.5](#45-add-a-plug) below for why).

Both of these are optional — you can run Husbandry Tracker purely as a logbook with no smart
devices at all, hand-entering readings and care events (see [Manual Sensor](#manual-sensor) and
[Manual Plug](#manual-plug) below).

---

## 2. First Launch

If you ran the installer, it already created a **Husbandry Tracker** shortcut on your Desktop and
launched it once for you — the dashboard should have opened in your browser a few seconds after
install finished. From now on, that same Desktop shortcut is how you start Husbandry Tracker.

Double-clicking the shortcut starts the website and three background processes (Ingest, the Govee
sensor listener, and the Tuya plug poller) with no console windows to manage, and opens the
dashboard in your browser automatically after a few seconds. You'll see a small icon appear in the
**system tray** (bottom-right of your screen, near the clock) — right-click it for a menu that lets
you **Open Dashboard**, **Start/Stop/Restart** each part individually, **View Logs**, or tick
**"Start with Windows"** so Husbandry Tracker comes up automatically every time you log in, the same
way apps like Docker Desktop or Steam do.

The tray icon turns **yellow** if something's restarting and **red** if something's failed
repeatedly and needs your attention — see [Section 15](#15-if-somethings-not-working) if that
happens.

Don't see the tray icon, or the dashboard didn't open? Double-click the Desktop shortcut again. If
there's still nothing, see [Section 15](#15-if-somethings-not-working).

---

## 3. The Dashboard at a Glance

The dashboard (`http://localhost:22255`, or whatever **Open Dashboard** takes you to) is a
glance-only screen — nothing to fill out here except a Manual Sensor's readings (see below).
Panels are grouped by **Room** (see [Section 7](#7-rooms-light-schedules-and-fallback-sensors)) —
each Room gets a heading showing its own ambient reading and Light Schedule, with its Enclosures'
panels underneath; any Enclosure not yet assigned to a Room lands in an "Ungrouped" section at the
end.

Each panel shows:

- **Enclosure name**, and each animal living in it (name, species, date of birth), at the top —
  click it to jump to that enclosure's own Admin page.
- **Readings** — the latest value from each of that enclosure's own Sensors. If it has none of its
  own but belongs to a Room, it instead shows that Room's Fallback Sensor reading, labeled "room"
  and always gray — that reading is real, but it's the room's general condition, not a judgment on
  whether it's right for that specific animal.
- **Care** — how long it's been since the enclosure was last fed, watered, spot-cleaned, and
  deep-cleaned. Click any of those (e.g. "3d ago", "never") to jump straight to that specific log
  entry on the enclosure's Admin page.
- **Plugs** — each Plug's current on/off status (or "Unreachable"), if you've chosen to show it (see
  [Choosing what shows on the Dashboard](#choosing-what-shows-on-the-dashboard) below).

Every Reading pill also carries a small **sparkline** chart underneath it — a one-week preview of
that exact Sensor's history, with its Target Range shaded in behind the data if one is set. It's
easy to miss the first time since nothing labels it as clickable: click it to open the full
[Graphs page](#9-viewing-history-view-data-and-graphs) for that Sensor, scrolled right to it.

Schedules (light/heat/cooling on-times) and the actual Care-logging buttons live on each
enclosure's own Admin page instead — see [Section 4](#4-setting-up-your-first-enclosure).

**Rearranging and collapsing.** You can drag an Enclosure's panel straight onto a different Room's
section (or onto "Ungrouped") to move it there — no form needed, same effect as changing its Room
from Enclosure Settings. Every Room heading, Enclosure panel, and inner subsection (Readings/Care/
Plugs) has its own ▾ collapse toggle; your browser remembers which ones you've collapsed between
visits. Care starts collapsed by default; Readings and Plugs start expanded.

### Forcing a fresh reading with "↻ Refresh"

A Room or Enclosure with at least one Smart (Govee) Sensor of its own gets a small **"↻ Refresh"**
button next to its name. Clicking it waits for a real live reading from that Sensor right now,
instead of whatever the background listener last happened to hear — real sensors only broadcast
every 10–60+ seconds, so this can take a little while (the browser just waits; that's normal). Only
ever refreshes what that Room/Enclosure actually owns — a Room's button never reaches into its
Enclosures, and an Enclosure showing a Room's Fallback Sensor reading has no button of its own (use
the Room's instead). How long it waits before giving up is the **Refresh Timeout** setting on the
Control Panel (default 30s — see [Section 10](#10-getting-notified-when-somethings-wrong)).

### What the colors mean

| Color | Meaning |
|---|---|
| 🟢 Green | All good — recently done / reading is in the target range |
| 🟡 Yellow | Getting close to due |
| 🔴 Red | Overdue / reading is outside the target range / never logged |
| ⚪ Gray | No data yet, or no target range has been set for that sensor |

### Logging a Manual Sensor's reading

A Manual Sensor (see [Manual Sensor](#manual-sensor) below) has no physical device feeding it data,
so it shows a small "Log Reading" form right under its row on the dashboard — enter whatever
value(s) you just measured and click it. There's a date/time box if you're logging a reading from
earlier rather than right now; leave it blank to log it as now.

---

## 4. Setting Up Your First Enclosure

Everything below happens on the **Admin** side of the app — click **Control Panel** or **All
Enclosures** in the top navigation bar (not **Dashboard**, which is view-only).

### 4.1 (Optional) Create a Room first

If several enclosures share a physical space (a rack, a shelf, a room with its own ambient
light), it's worth creating that **Room** before adding enclosures into it, so you can assign them
as you go rather than coming back later. If you only have one or two enclosures and no shared
ambient sensor between them, feel free to skip this and come back to [Section
7](#7-rooms-light-schedules-and-fallback-sensors) later — a Room is entirely optional.

1. Go to **Control Panel** (`/admin`).
2. In the **Rooms** card, fill out **"+ Add Room"** — just a name (e.g. "Reptile Rack") — and click
   **Create**.

### 4.2 Add an Enclosure

1. Go to **All Enclosures** (`/admin/enclosures`).
2. Fill out the **"+ Add Enclosure"** form at the bottom:
   - **Name** — whatever you call the tank (e.g. "Gargoyl", "The Cape").
   - **Enclosure Type** — **Basic** (snake/lizard/tortoise/insect — the default), **Freshwater**,
     **Saltwater**, or **Amphibian**. This decides which Target Range fields you'll be offered when
     you add a Sensor in a moment: Basic and Amphibian offer temperature, humidity, and UVB Index;
     Freshwater/Saltwater/Amphibian add water-chemistry fields instead (pH, ammonia, nitrite,
     nitrate, and — Saltwater only — specific gravity, salinity, alkalinity, calcium, magnesium,
     phosphate). You can change this later from Enclosure Settings if you got it wrong; it just
     changes which fields show, nothing already saved is erased.
   - **Bioactive** — check this box if it has a live cleanup crew (isopods, springtails, live
     plants). Besides relaxing how often a Deep-clean is expected, this also unlocks a **Plants**
     card — see [Section 6](#6-bioactive-enclosures-and-plants).
   - **Feeding / Watering / Spot-clean / Deep-clean interval** — how many days between each, for
     this enclosure. This is what drives the green/yellow/red colors, so set it to match how you
     actually care for that animal (a snake might be fed weekly; a small gecko might need feeding
     every 2–3 days).
3. Click **Create** — it takes you straight to that enclosure's own Admin page, where everything
   else below happens.

A new enclosure lands in "Ungrouped" on the dashboard until you give it a Room — see [Section
7](#7-rooms-light-schedules-and-fallback-sensors) for how, or just drag its dashboard panel onto a
Room later.

### 4.3 Add an Animal to It

On the enclosure's own page, fill out the **"Add Animal"** form: name, common species name,
scientific name (optional), and date of birth (exact date, or just a year-month like `2024-05` if
you don't know the exact day). Click **Create**.

Each Animal gets a small "edit" link, which is also where you'll go to log its Weight, Length,
Count, or Condition over time — see [Section 5](#5-tracking-an-animals-growth-and-condition).

### 4.4 Add a Sensor

Every Sensor is either **Smart** (a real Govee device, read automatically) or **Manual** (no
device — you log readings by hand). An enclosure can have more than one — a common setup is one on
the warm side and one on the cool side, each with its own label and target range.

#### Smart Sensor (Govee)

1. On the enclosure's own Admin page, in the **"Add Sensor"** form, leave **Tracking Mode** on
   **Smart**.
2. Click **Discover Devices**, next to the MAC address field. Wait about 20 seconds while it
   listens for nearby Govee sensors — put the Govee Home app in the foreground on your phone too,
   so you can cross-check readings live.
3. Click whichever device in the results list is the one you mean (each shows a live temperature/
   humidity reading, so you can match it against what that enclosure's sensor is actually reading
   right now) — that fills in the MAC address field for you.
4. Give it a label (e.g. "warm side").
5. Optionally set a target range (min and max) on whichever metric it measures — that's what turns
   its reading green or red on the dashboard.
6. Click **Create**.

See [How To: Add a Govee Sensor](HOWTO_ADD_GOVEE_SENSOR.md) for this same walkthrough end to end,
including pairing the sensor in the Govee Home app first.

**Already have a Manual Sensor and just got the real Govee hardware?** You don't need to re-create
it — open that Sensor's **Edit** page, switch **Tracking Mode** to **Smart**, and the same
**Discover Devices** button appears next to the MAC address field there too.

#### Manual Sensor

For a spot-check tool with no Bluetooth of its own (an infrared thermometer, a moisture meter, a
water test strip):

1. In the **"Add Sensor"** form, set **Tracking Mode** to **Manual**.
2. Give it a label.
3. Set a target range (**min *and* max**) on whichever metric it measures — this is required for a
   Manual Sensor, since there'd otherwise be nothing to judge a hand-logged reading against.
4. Optionally change its **Volatility** (Default/Fast/Slow) next to that metric — this records
   whether the real-world value swings meaningfully within a day (Fast — temperature, pH) or only
   over about a week (Slow — calcium, salinity). It's here and saved, but doesn't change anything
   visible on Graphs/Sparkline yet, so don't worry if you don't see an effect.
5. Click **Create**. Its dashboard row now grows a small "Log Reading" form you use whenever you
   take a measurement.

**Have a Tuya/Smart-Life temperature/humidity sensor (with or without a probe), not a Govee
device?** That's a different product than what's covered above, and isn't read automatically yet —
see [How To: Add a Tuya Zigbee Temp/Humidity/Probe
Sensor](HOWTO_TUYA_TEMP_HUMIDITY_PROBE_SENSOR.md) for exactly what works today (short version: it's
a Manual Sensor for now).

### 4.5 Add a Plug

Unlike Animals/Sensors (added from the Enclosure or Room they belong to), Plugs are added from the
**Control Panel** (`/admin`), in its own **"Plugs"** card — a Plug can belong to more than one
place, which is why it lives at the top level rather than nested under one Enclosure.

Every Plug is either **Smart** (a real Tuya-controlled Gosund plug, read automatically) or
**Manual** (no smart device — e.g. a light on a mechanical timer); pick which one in the **"Add
Plug"** form's Tracking Mode dropdown.

**Belongs to** is where you say what a single physical Plug controls:
- **Enclosure(s)**: check the box next to each Enclosure it serves. Almost always just one; check
  more than one when a single physical switch controls several tubs at once ("everything on one
  switch").
- **Room**: for a genuinely room-wide fixture (a rack's ambient light) that isn't tied to any
  specific tub.

A Plug always belongs to exactly one of those, never both, never neither.

#### A one-time account-linking step for a Smart Plug

Unlike a Govee sensor's ID (a plain Bluetooth broadcast — see **Discover Devices** above), a
Gosund plug's **device ID** and **local key** only exist in Tuya's own cloud — no scan can find
them. The one unavoidable step, done **once** no matter how many plugs you add afterward, is
linking a free Tuya developer account to the same account you paired the plug with in Smart Life:

1. Go to [iot.tuya.com](https://iot.tuya.com) and create a free account.
2. Create a "Cloud" project there and link it to your Smart Life account (usually a QR-code scan
   from your phone).
3. On Husbandry Tracker's Control Panel, find the **Tuya Cloud Credentials** card and paste in the
   **Access ID** and **Access Secret** the project's page shows you, pick the matching **API
   Region**, and click **Save**. The Access Secret is never shown again once saved.

No Python, no Command Prompt. See [How To: Add a Gosund Smart Plug](HOWTO_ADD_GOSUND_PLUG.md) for
the full walkthrough, including pairing the plug in Smart Life first — **this is the one setup step
worth doing with an extra pair of hands the first time.**

#### Smart Plug (Gosund)

**Not Google Home** — pair the plug in the **Smart Life** app (or Tuya Smart — either works), since
Google Home has no way to hand Husbandry Tracker the credentials it needs, even though it can also
control the same plug.

1. On the **"Add Plug"** form, set **Tracking Mode** to **Smart**, give it a label (e.g. "UTH",
   "basking bulb"), and pick a **Purpose** (light/heat/cooling/etc. — free text, type whatever fits).
2. Click **Discover Devices**, then click this plug from the list — that fills in the **device ID**
   and **local key**, plus a best guess at **Outlet / DPS key** (double-check against
   `tools/tuya_probe.py` if unsure — see the how-to above). Leave it as `1` unless the plug is a
   multi-outlet power strip — see [Section 8](#8-grouping-outlets-on-a-power-strip-plug-groups) for
   those.
3. Leave the IP address blank unless a plug keeps failing to connect, in which case pinning its IP
   can help.
4. Set **Belongs to** (above), and click **Create**.

**Already have a Manual Plug and just got the real Gosund hardware?** Open that Plug's **Edit**
page, switch **Tracking Mode** to **Smart**, and the same **Discover Devices** button appears
there too (once Tuya Cloud Credentials, above, are saved).

#### Manual Plug

For a light/heat source switched by hand or by a plain mechanical timer with no smart features:

1. In the **"Add Plug"** form, set **Tracking Mode** to **Manual**.
2. Give it a label and a **Purpose**.
3. Enter the timer's on-time and off-time (or check **Always On** instead — see below — if it just
   runs continuously, like a filtration pump).
4. Set **Belongs to**, and click **Create**.

#### Controller Kind, and Always On

If a heat/cooling Plug actually powers a separate thermostat unit (a Herpstat, Vivarium
Electronics, Jump Start, etc.) rather than the heat source directly — or a humidity Plug powers a
separate humidity controller rather than the moisture source directly — set its **Controller Kind**
to **Thermostat-Controlled** or **Hydrostat-Controlled** when adding or editing it, and enter the
matching **Target Temperature** or **Target Humidity** you've set that controller to. Either way,
the controller's actual on/off cycling happens downstream, invisible to Husbandry Tracker, so the
Target value is the one thing that's actually meaningful to record — this doesn't judge whether the
enclosure is actually at that temperature/humidity, that's still a real Sensor's Target Range, if
you have one in there.

Only shown when Controller Kind is "none": an **Always On** checkbox, for a Plug meant to run
continuously with no on/off cycle at all (a filtration pump). Checking it disables the Target
Schedule fields — a Plug has one, the other, or neither, never both.

**Reassigning a plug already sitting in "Unassigned"**: open its edit page from the Plugs list,
check the box(es) for its real Enclosure(s) (or switch "Belongs to" over to Room), fix the
label/Purpose, and save — no need to re-enter the device ID or local key, those stay attached to
the physical plug. A Plug lands back in Unassigned on its own if it ever loses its last Enclosure
(e.g. that Enclosure gets deleted) — it's a safety net, not something you manage directly.

### 4.6 Turning a Plug On or Off by Hand

Open a Plug's own edit page (from the Control Panel's or an Enclosure's Plugs list) or, for a
Room-owned Plug, go to that Room's own **Schedules** card — either way you'll find **Turn On** /
**Turn Off** buttons. Clicking one sends the command right away (no confirmation dialog), useful
for reacting quickly to an alert or just checking a bulb works.

If that Plug has a **determined setting** — a Controller Kind other than none, a Target Schedule,
or Always On — the button also reveals an optional note field first. That's because you're
deliberately interrupting something the Plug is expected to return to on its own; the note is
there if you want to record *why* (e.g. "pulled early for a feeding check"), but it's entirely
skippable. A plain Plug with none of those settings just toggles straight away, no note prompt.

### 4.7 Logging that You Fed, Watered, or Cleaned an Enclosure

Each enclosure's Admin page has a **Care** card at the top. Click **Today**, **Yesterday**, or **2
days ago** next to Feeding, Watering, Spot-clean, or Deep-clean — whichever it actually was. For
anything further back, click **Advanced** to get the full date/time picker.

**Feeding just one animal (spot-feeding)**: if an enclosure holds more than one animal (a community
tank, a pair), the Feeding row also shows a dropdown of that enclosure's animals, next to "Whole
enclosure." Pick a specific animal before logging — e.g. dropping an extra pellet for one
underweight fish in a community tank, without logging it as feeding the whole tank. Leave it on
"Whole enclosure" (the default) for the ordinary case of feeding everyone at once. Watering,
Spot-clean, and Deep-clean don't have this option — those always apply to the whole enclosure.

### Choosing what shows on the Dashboard

Every Animal, Sensor, and Plug has a small **"On Dashboard"** checkbox on its own list, right where
you added it (and each of the four Care kinds has its own checkbox inside Enclosure Settings, next
to its interval). Ticking or unticking it takes effect immediately — no separate Save button. New
rows default to shown for the first three registered under the same parent, and off after that, to
keep an Enclosure or Room with a lot of sensors from overwhelming the dashboard; flip any of them
either way at any time, the default only applies the moment a row is created.

---

## 5. Tracking an Animal's Growth and Condition

On an Animal's own edit page (the "edit" link next to its name wherever it's listed), below its
name/species/date-of-birth, is a **Growth & Condition Log**: a history table (newest first)
showing every Weight, Length, Count, and Condition entry you've logged for that animal, and four
small forms underneath for adding a new one:

- **Log Weight** (grams)
- **Log Length** (centimeters)
- **Log Count** — how many individuals this Animal row actually represents right now (e.g. a coral
  head cluster or a school of small breeding fish counted as one row)
- **Log Condition** — a coarse, subjective pick (Poor / OK / Good / Really Good) plus an optional
  free-text note

Each of the four is independent — a given day might get just a Weight entry, or just a Condition
note, without the others. Each form has its own optional "When" field if you're logging something
from earlier rather than right now.

---

## 6. Bioactive Enclosures and Plants

Once an enclosure is checked **Bioactive** (in Enclosure Settings), its Admin page grows a
**Plants** card. This is entirely optional — you can log Plant Health for the enclosure as a whole
without ever naming an individual plant, or track specific ones by name, whichever fits how closely
you watch them.

- **Adding a Plant**: fill out **"+ Add Plant"** — a name (e.g. "pothos", "left-side moss") and
  optionally a species. Each one gets a **remove** link once added.
- **Logging Plant Health**: the same card has a **Plant Health log** further down — pick a specific
  Plant from the dropdown (or leave it on "(whole enclosure)"), type what you observed (e.g.
  "pothos yellowing, moved out of direct light"), and click **Log**. There's a date/time box if
  you're logging something you noticed earlier. The most recent entries show in the table above the
  form.

An enclosure with Bioactive unchecked has no Plants card at all — check that box first (Enclosure
Settings, at the top of the enclosure's page) if you don't see it.

---

## 7. Rooms, Light Schedules, and Fallback Sensors

A **Room** groups Enclosures that share a physical space (e.g. "Living Room", "Reptile Rack"). It's
optional — an Enclosure with no Room behaves exactly as before.

On the **Control Panel**, fill out the **"+ Add Room"** form (just a name). Click into the new
Room's own page to add:

- **Sensors** — its own ambient Sensor(s) (Smart or Manual, same forms as an Enclosure's), for
  measuring the room as a whole rather than any one tank.
- **Light Schedule** — an on-time/off-time for the room's general lighting, plus a free-text note
  for anything else worth capturing (e.g. "natural light from east window", "dimmed after 6pm").
- **Plugs** and **Schedules** for anything room-wide — see [Section
  4.6](#46-turning-a-plug-on-or-off-by-hand) for the Turn On/Off buttons here.

To put an Enclosure in a Room, either drag its panel onto that Room's section on the dashboard, or
go to the Enclosure's own Admin page and pick it from the **Room** dropdown in Enclosure Settings.

**Fallback Sensor**: if an Enclosure has no Sensor of its own but belongs to a Room, its Enclosure
Settings form grows a **Fallback Sensor** dropdown listing that Room's Sensor(s) — pick whichever
one sits physically closest to that Enclosure. The dashboard will then show that Sensor's reading on
the Enclosure's own panel (clearly labeled, always gray — see [Section
3](#3-the-dashboard-at-a-glance) for why). If the Enclosure later gets a real Sensor of its own,
that always takes priority and the Fallback Sensor stops being used.

---

## 8. Grouping Outlets on a Power Strip (Plug Groups)

If you have a multi-outlet Tuya power strip — several independently-switched relays sharing one
physical device and one "master" on/off button — a **Plug Group** gives its outlets a shared
identity in the UI instead of a handful of unrelated-looking Plug rows.

On the **Control Panel**, the **"Plug Groups"** card sits above the plain "Plugs" card.

**Creating one**: fill out **"+ Add Plug Group"** — a name, **Belongs to** (same Enclosure/Room
choice as any Plug), and the strip's one shared Tuya device ID/local key/IP. Today there's one
layout to choose from: 3 independently-switched relay outlets, 1 USB outlet, and 3 always-on
outlets with no relay at all (hardwired straight to mains). Each outlet gets a pre-filled, fully
editable label and purpose before you save — fix the DPS key too if your strip numbers its relays
differently.

**Using one**: each group shows as its own card listing its member outlets, with **All On** / **All
Off** buttons that send the command to every Smart outlet in the group at once (always-on outlets
have nothing to toggle, so they're skipped). **Delete Group** ungroups the member Plugs rather than
deleting them — they become ordinary standalone Plugs, keeping their own history.

**Attaching an existing Plug to a group**, or moving one in from the regular "Add Plug" form:
either pick the group from the **Plug Group** dropdown while creating a new Plug (it then inherits
the group's Enclosure/Room and Tuya credentials — you only set its own outlet/DPS key), or, for a
Plug you already have, open its own edit page and use its own **Plug Group** dropdown there.

---

## 9. Viewing History: View Data and Graphs

Every Enclosure's and Room's own Admin page has **"View Data"** and **"Graphs"** buttons near the
bottom, for looking back at everything that's been logged or collected for it.

### View Data

Opens an index page listing one title per Sensor reading, Care Event kind, Animal Log field, and
Plug status/telemetry metric — titles only, no dates or values. Click one to open its detail page:
every real entry behind it, newest first, with **Edit** and **Delete** wherever the underlying row
is something you actually hand-entered (a Manual Sensor's Reading, a Care Event, an Animal Log
entry). A Smart Sensor's Reading and a Plug's auto-collected status/telemetry are shown read-only —
there's nothing to correct, since nobody typed them in.

**Adding a new entry** on an editable row: pick a date, then either a **Period Slot** (Morning /
Afternoon / Night) or, for a Care Event only, **"Exact time…"** if you actually know the precise
time. A Period Slot is for when you know roughly when something happened but not the exact minute
— it's a real, if coarse, fact about when it happened, not a guess. Care Events also get an
optional note, and, for a Feeding on an enclosure with animals, the same spot-feed Animal picker
described in [Section 4.7](#47-logging-that-you-fed-watered-or-cleaned-an-enclosure).

### Graphs

The same rows as View Data, charted instead of tabled. A Range dropdown (Week/Month/90 Days/180
Days/Year) with **« Prev** / **Next »** paging controls what window you're looking at. Every row
draws its own small chart; a numeric one (a Reading, a Plug telemetry metric, an Animal Log number)
draws as a line, and anything without a Y-value of its own (a Care Event, a Plug status change, an
Animal Log Condition) draws as a marker along the timeline instead.

**Overlay**: check two or more rows in the picker near the top, and a combined chart layering just
those series on one shared timeline appears above everything else — handy for comparing, say, two
Sensors' temperature readings, or a Plug's on/off history against a Sensor's reading right next to
it. Nothing here is saved between visits; build the combination again whenever you want it.

---

## 10. Getting Notified When Something's Wrong

Besides coloring things red on the dashboard, Husbandry Tracker can push a notification straight to
your phone when a Sensor reading goes out of range, a heat/cooling Plug is switched on but not
actually drawing power (a burnt-out bulb or failed element), or a Smart Sensor/Plug stops reporting
altogether. This only checks Smart Sensors/Plugs with Auto-Update on (see [Section
11](#11-pausing-a-device-without-removing-it)) — Manual ones have nothing automatic to watch.

It only fires after a problem has stuck around for a while (10 minutes by default, not the instant
it's first noticed) — a single noisy reading or a momentary network blip won't wake you up for
nothing. You'll also get a second notification once things are back to normal, so you know both
when something broke and when it got fixed.

**Setting it up** uses **[ntfy](https://ntfy.sh)**, a free, no-account-needed push notification
app:

1. Install the **ntfy** app on your phone (search your phone's app store) — or use
   [ntfy.sh](https://ntfy.sh) in a browser if you'd rather.
2. In the app, **subscribe to a topic** — pick any name nobody else is likely to guess (it's not
   password-protected, so something like `husbandrytracker-yourname-4821` is safer than plain
   `husbandrytracker`). This is like a private radio channel: whoever subscribes to the same topic
   name gets the same notifications.
3. On the **Control Panel**, in the **Settings** card at the top, enter:
   - **ntfy Server URL**: `https://ntfy.sh` (unless you're self-hosting your own ntfy server)
   - **ntfy Topic**: the exact topic name you subscribed to
   - **Alert Debounce (minutes)**: how long a problem has to persist before you're notified
     (default 10)
4. Click **Save**.

Leave the ntfy fields blank to turn notifications off entirely — Husbandry Tracker still tracks
whether things are OK internally, it just won't push anything to your phone.

One current gap, so it's not a surprise: the "Plug switched on but not drawing power" check needs
wattage readings to compare against, and none of the currently-supported Gosund plug models report
that over the local connection this app uses — so that one check never fires yet. Out-of-range
Sensor readings and unreachable-device notifications both work today regardless.

### Timer Warning

Separately from Send Alert, a Smart Plug's own edit page shows its **Detected Schedule** — the
actual on-time and off-time Husbandry Tracker has observed from watching it, once it's seen at
least one full on/off cycle (until then it says "no data yet," which is expected, not an error).
If the Detected times drift from the Target Schedule you declared by more than the **Schedule
Drift Threshold** (an app-wide setting in the Control Panel's Settings card, default 15 minutes),
the drifting time shows in red with a **Timer Warning** pill, visible there and wherever that Plug
is listed. Click **Clear warning** once you've acknowledged it — it goes neutral again until the
schedule drifts to a genuinely different time.

---

## 11. Pausing a Device Without Removing It

Every Smart Sensor or Smart Plug's edit page has an **Auto-Update** checkbox, checked by default.
Uncheck it to pause that device's background collection — no more Readings, on/off tracking, or
Send Alert checks for it — without losing its setup (MAC address, device ID, local key, target
ranges, everything). Check it again any time to resume.

Use this for a device that's temporarily not telling you anything useful: a sensor pulled out for
cleaning, a plug unplugged for the season, or one that's gone flaky and keeps triggering Send Alert
notifications you don't need right now. It's not the same as switching Tracking Mode to Manual —
that's for permanently swapping the physical hardware; Auto-Update is for a temporary pause on the
same device. Pausing takes effect within a few seconds either way — the next time its plugin polls
or hears from it, it checks whether you've paused it first.

Sending a Plug a Command, or clicking its Probe button (next to its Data Capture line, for a quick
raw diagnostic look at what the device is currently reporting), resumes Auto-Update automatically if
it was paused.

---

## 12. Removing Something

Every animal and sensor has a small **"remove"** link next to it, and a Plug has a **"Delete
Plug"** button on its own edit page. There's also a **"Delete Enclosure"** button on the
enclosure's page (and a matching one for a Room), which removes everything that belongs
*exclusively* to it — it asks you to confirm first, since that can't be undone. A Plug shared with
other Enclosures just loses that one link and keeps going; see "Reassigning a plug" in [Section
4.5](#45-add-a-plug) for what happens if it loses its last one. Deleting a Plug Group ungroups its
member Plugs rather than deleting them — see [Section
8](#8-grouping-outlets-on-a-power-strip-plug-groups).

---

## 13. Stopping Husbandry Tracker

Right-click the tray icon and choose **Stop All**, or **Quit** to also close the tray icon itself.
(Quit is what you want before updating the software; Stop All leaves the tray icon running so you
can Start All again from the same menu later.)

You don't strictly need to stop anything — it's fine to leave it running all the time (that's
actually the normal way to use it, so history keeps accumulating, and "Start with Windows" assumes
you will). Stopping is only needed if you're restarting the computer, updating the software, or
troubleshooting.

---

## 14. Backing Up and Restoring Your Data

Everything Husbandry Tracker knows — enclosures, animals, readings, feeding/watering/cleaning
history, and your sensors' and plugs' device credentials — lives in one file. Husbandry Tracker
backs it up for you automatically, and you can also trigger one yourself right before doing
anything that makes you nervous (like uninstalling, reinstalling, or moving to a new computer).

### Automatic backups

Once a day, while Husbandry Tracker is running, it quietly saves a backup to a `backups` folder
inside wherever Husbandry Tracker is installed. You don't need to do anything for this to happen.
Backups older than 14 days are cleaned up automatically so this folder doesn't grow forever.

### Backing up before doing something risky

Right-click the tray icon and choose **Back Up Now**. It takes a few seconds (up to about 5) to
actually happen — you don't need to wait or watch for anything, it just happens in the background.
Good moments to do this: right before uninstalling, right before updating to a new version, or any
time you just want extra peace of mind.

### If you uninstall and reinstall on the same computer

You don't need to do anything — uninstalling Husbandry Tracker never deletes your data, only the
program itself. Reinstalling to the same location picks your existing data back up automatically.

### Moving to a new computer, or recovering from a drive failure

Automatic backups live on the same drive as Husbandry Tracker itself, so they won't survive that
drive failing. For real protection, copy the `backups` folder (or just its newest file) somewhere
else — a USB drive, or a folder that syncs to OneDrive or a similar service — the same way you'd
back up any other important file. Copy it to the new computer's Husbandry Tracker installation
folder before you start using it there, and it'll be picked up the next time you use **Restore from
Backup** (below).

### Restoring from a backup

Right-click the tray icon, choose **Restore from Backup**, and pick the one you want from the list
(most recent first, with the date and time it was made). Confirm when asked — this stops Husbandry
Tracker, saves your *current* data as one more backup first (so this itself isn't a one-way door),
then swaps in the one you picked and starts everything back up. Takes a few seconds.

---

## 15. If Something's Not Working

- **Windows shows a blue "Windows protected your PC" screen when running
  `HusbandryTrackerSetup.exe`** — Expected, not a sign anything's wrong. Husbandry Tracker is a
  small open-source project without a paid code-signing certificate, so Windows doesn't yet
  recognize it as a well-known publisher. Click **More info**, then **Run anyway** to continue
  installing.
- **The website won't load at `localhost:22255`, or a reading is stuck on "no data yet"** —
  Right-click the tray icon and check for a red (failed) or yellow (restarting) status; click
  **Start** on whichever part shows it, or **View Logs** to see why it's been crashing. If the tray
  icon itself isn't there at all, double-click the Husbandry Tracker Desktop shortcut again. Also
  double check Bluetooth is turned on (the sensor listener needs it).
- **A reading looks obviously wrong** (like a huge negative number) — Let us know rather than
  trusting it; that's a sign the sensor decoding needs another look for that specific device.
- **A Smart Plug never reports wattage/voltage/current, or Send Alert never catches a burnt-out
  bulb** — Expected for now; see the note in [Section 10](#10-getting-notified-when-somethings-wrong).

---

## Appendix A: Running From Source

Husbandry Tracker is open source — clone the repo and run it directly with Python instead of using
the installer, whether for development, or because you're on a platform other than Windows (note:
Bluetooth/Tuya support is currently only exercised on Windows).

### One-time setup

1. Get the project folder onto the computer:
   ```
   git clone https://github.com/caskabove/HusbandryTracker.git
   cd HusbandryTracker
   ```
2. Set up Python's workspace (this only needs to happen once):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   You'll know it worked if you see a list of package names scroll by with no red error text at
   the end.
3. Run `python tray\install.py` to create a Desktop shortcut, same as the installer does — from
   here on, everything in this guide (starting with [Section 2](#2-first-launch)) applies exactly
   the same way.

### Running each part by hand

Useful if you want to see what's actually happening without going through the tray icon. Every time
you want to use Husbandry Tracker this way, you start **four things**, each in its own Command
Prompt window:

**Website:**
```
.venv\Scripts\activate
python -u -m uvicorn web.main:app --host 127.0.0.1 --port 22255
```

**Ingest** (a second Command Prompt window):
```
.venv\Scripts\activate
python -u ingest\ingest.py
```

**Sensor plugin** (a third Command Prompt window):
```
.venv\Scripts\activate
python -u plugins\govee_ble\plugin.py
```

**Plug plugin** (a fourth Command Prompt window):
```
.venv\Scripts\activate
python -u plugins\tuya_lan\plugin.py
```

Then open a web browser to `http://localhost:22255`. This only works on the computer Husbandry
Tracker is running on (that's intentional — it's a private, local-only dashboard, not accessible
from other devices or the internet).

### The Desktop shortcut didn't appear after running `python tray\install.py`

`install.py` asks Windows itself where your Desktop is and puts the shortcut there, so if nothing
shows up, your Desktop folder is almost certainly somewhere other than the plain
`C:\Users\<you>\Desktop` you'd expect — common with OneDrive's "back up your folders"/Known Folder
Move feature, or if someone manually relocated it via a folder's Properties dialog. To check and
fix:

1. Open **File Explorer**, right-click **Desktop** in the left sidebar (under Quick Access or This
   PC), choose **Properties**, and open the **Location** tab. It'll show where Windows currently
   thinks your Desktop is — if that's not where you were looking, that's the mismatch.
2. If you want it back to normal, click **Restore Default**, then **Apply**. Windows may say the
   default folder (`C:\Users\<you>\Desktop`) doesn't exist yet — that's expected if it's never been
   used before; let it create the folder.
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
