# How To: Add a Govee Sensor

This covers Govee's small Bluetooth temperature/humidity sensors (the **H5074** and **H5102** are
the two models Husbandry Tracker currently understands) — the kind you stick inside an enclosure with no
probe, no WiFi, and no hub: just a battery and a Bluetooth radio that broadcasts a reading every
10-60+ seconds for anything nearby to pick up.

**Read this first:** unlike the Tuya Zigbee sensor covered in a [separate
how-to](HOWTO_TUYA_TEMP_HUMIDITY_PROBE_SENSOR.md), this device needs **no hub, no gateway, and no
WiFi at all** — it's Bluetooth Low Energy (BLE), a different radio again, and it's the one device
type Husbandry Tracker already reads fully automatically.

**Contents**
1. [What You Need](#1-what-you-need)
2. [Add Govee Device (One-Time, in the Govee App)](#2-add-govee-device-one-time-in-the-govee-app)
3. [Finding the Sensor's ID](#3-finding-the-sensors-id)
4. [Adding It to Husbandry Tracker](#4-adding-it-to-husbandry-tracker)
5. [Using It Day to Day](#5-using-it-day-to-day)

---

## 1. What You Need

- **The sensor itself** (Govee H5074 or H5102), with its battery in.
- **The Govee Home app** on your phone — free, from your phone's app store (search "Govee Home").
  You only need this app **once**, to confirm the sensor works and get its readings showing on your
  phone — after that, Husbandry Tracker listens to it directly and you never need to open the app again
  for this sensor.
- **The computer running Husbandry Tracker** needs Bluetooth turned on, and needs to stay physically near
  the sensor (Bluetooth's range is much shorter than WiFi's) — see `docs/USER_GUIDE.md` section 1
  for the full "what the computer needs" list.
- **No hub, no gateway, no router setup** — unlike the Tuya sensor, there's nothing else to buy.

---

## 2. Add Govee Device (One-Time, in the Govee App)

1. Open the **Govee Home** app and create a free account if you haven't already.
2. Tap **Add Device** (usually a "+" icon), and either let the app auto-detect the sensor nearby, or
   pick its category by hand (something like "Thermometer/Hygrometer").
3. Follow the on-screen pairing steps — this is a direct Bluetooth connection from your phone to the
   sensor, no WiFi credentials needed.
4. Confirm you can see a live temperature/humidity reading on the sensor's card in the app before
   moving on.

*(If any of these exact screens or button names don't match what you actually see, let me know — this
section is written from how Govee's standard pairing flow normally works, not a verified run-through,
and I'd rather fix it than leave it wrong.)*

---

## 3. Finding the Sensor's ID

This is the one step that needs a short detour into a Command Prompt, because finding a Govee
sensor's ID isn't something the Husbandry Tracker website can do on its own yet.

1. Open a Command Prompt in the Husbandry Tracker folder, and run:
   ```
   .venv\Scripts\activate
   python tools\govee_discover.py 20
   ```
2. Wait 20 seconds. It'll print a list of nearby Govee sensors, each with a code like
   `E3:60:59:23:50:A6` — that's the sensor's ID (its "MAC address").
3. To figure out *which* sensor belongs to *which* enclosure: check the current reading it prints
   against what the Govee Home app (or the sensor's own little screen) shows for that enclosure —
   they should match.

---

## 4. Adding It to Husbandry Tracker

1. On Husbandry Tracker's Admin page, go to the enclosure this sensor belongs in.
2. In the **"Add Sensor"** form, leave **Tracking Mode** on **Smart**.
3. Paste in the sensor's ID from step 3 above, and give it a label (e.g. "warm side").
4. Optionally set a target temperature/humidity range — that's what turns the Temp/Humidity numbers
   green or red on the dashboard.
5. Click **Create**.

---

## 5. Using It Day to Day

Nothing to do — once added, Husbandry Tracker listens for this sensor's Bluetooth broadcasts in the
background and updates its reading automatically, no app needed. Use the dashboard's **"↻
Refresh"** button if you want a fresh reading right now instead of waiting for the next automatic
one (see `docs/USER_GUIDE.md` section 4). If you have Send Alert set up, you'll also get notified if
this sensor's reading goes out of range or it stops reporting altogether.
