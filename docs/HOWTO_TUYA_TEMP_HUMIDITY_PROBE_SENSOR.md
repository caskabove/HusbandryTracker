# How To: Add a Tuya Zigbee Temp/Humidity/Probe Sensor

This covers the small thermometer/hygrometer sensors sold under names like "Smart Thermometer
Hygrometer with Probe" — they have a little screen, a 1-meter probe on a cable for a second reading
(inside an aquarium, a fridge, etc.), and are set up through the **Tuya Smart** app.

## ⚠️ Before you buy or open the box: this needs a separate hub, and the box may not make that obvious

This is a **Zigbee** device, not a WiFi device — Zigbee is a different, short-range wireless radio
that **cannot connect to your phone, your router, or the internet directly**. It only ever talks to
a nearby **Tuya Gateway** (sold as a "Tuya Multi-Mode Gateway," "Zigbee Gateway/Hub," etc.) — a
separate, small piece of hardware that plugs into power and *your* router, and acts as a translator
between the Zigbee sensor and the Tuya Smart app/cloud.

**If you don't already own one of these gateways, this sensor cannot be set up at all — no app,
no QR code, no amount of retrying will get around that.** This is easy to miss because many Tuya
product boxes and listings carry the same generic "get the Tuya Smart app" QR code regardless of
whether the device inside is a self-contained WiFi gadget or a Zigbee one that needs a hub — the
code just links to the app store, it doesn't mean the device works standalone. Check the box/listing
for the words "Zigbee" and "Gateway required" *before* assuming this is a simple scan-and-go setup.

If this is your first Zigbee device, you'll need to buy a Tuya-compatible gateway separately (often
sold alongside these sensors, or as its own "Tuya Zigbee Hub" product) before anything below will
work.

**Read this next:** even once it's working perfectly in the Tuya Smart app, this is a different kind
of device than the smart plugs HerpMonitor already tracks automatically. Right now, HerpMonitor
**cannot read this sensor's data on its own** — you'll still get full use of it in the Tuya Smart
app, but inside HerpMonitor it has to be logged by hand. See [What HerpMonitor can and can't do with
it](#what-herpmonitor-can-and-cant-do-with-it) below for exactly what that means day to day.

**Contents**
1. [What You Need](#1-what-you-need)
2. [Add Tuya Gateway Device (Once, Shared by All Your Zigbee Sensors)](#2-add-tuya-gateway-device-once-shared-by-all-your-zigbee-sensors)
3. [Add Tuya Device (the Sensor Itself)](#3-add-tuya-device-the-sensor-itself)
4. [Adding It to HerpMonitor](#4-adding-it-to-herpmonitor)
5. [Using It Day to Day](#5-using-it-day-to-day)
6. [What HerpMonitor Can and Can't Do With It](#what-herpmonitor-can-and-cant-do-with-it)

---

## 1. What You Need

- **A Tuya-compatible Zigbee gateway/hub**, already purchased — see the callout above. If you have
  more than one Zigbee sensor (or plan to), you only need **one** gateway; every Zigbee sensor in
  range pairs to the same hub.
- **The sensor itself**, plugged in or with batteries in, powered on.
- **The Tuya Smart app** on your phone — free, from your phone's app store (search "Tuya Smart").
  Some of these sensors list "Smart Life" as an alternative app instead; either works the same way,
  just use whichever one the sensor's box or included instructions point you to.
- **The gateway connected to 2.4GHz WiFi** — this is where the 2.4GHz-only limitation actually
  applies (the sensor itself has no WiFi radio at all, only Zigbee):

  > ⚠️ **Most home WiFi routers broadcast two networks: one 2.4GHz, one 5GHz — often under the same
  > name, so you can't always tell which one you're on.** The gateway (like most inexpensive smart
  > home hubs) can **only** join a 2.4GHz network. If the gateway's setup seems to hang, fail partway
  > through, or the app can't find it, this is the first thing to check — not a sign you did
  > something wrong. If your router's app or settings let you split the two networks into
  > differently-named WiFi names (e.g. "MyWiFi" and "MyWiFi_5G"), do that once, then connect your
  > phone (and make sure the gateway joins) the plain 2.4GHz one. If you're not sure how, your router
  > manufacturer's app or a quick web search for your router's exact model plus "separate 2.4GHz and
  > 5GHz" will walk you through it.

---

## 2. Add Tuya Gateway Device (Once, Shared by All Your Zigbee Sensors)

Skip this whole section if your gateway is already set up and showing as online in the Tuya Smart
app — you only ever do this once, not per sensor.

1. Plug the gateway into power and into your router (usually a cable, some are WiFi-only — follow
   its own included instructions for that part).
2. Open the **Tuya Smart** app and tap **Add Device**. Scroll down through the categories/device
   list until you find the gateway (often listed under "Gateway Control" or similar), and select it.
3. Follow the app's on-screen pairing steps for the gateway itself — this is the step that needs
   2.4GHz WiFi (see the callout above).
4. Confirm the gateway shows as **online** in the app before moving to the next section — a sensor
   can't be added to a gateway that isn't online yet.

---

## 3. Add Tuya Device (the Sensor Itself)

1. Put the sensor into pairing mode first — usually holding down a button on the sensor for a few
   seconds, or it may auto-enter pairing mode for a short window right after you put in batteries/
   power it on for the first time. Check the sensor's own included instructions for the exact
   button/timing, since this varies by model.
2. In the Tuya Smart app, tap **Add Device** (the same button used for the gateway above). Scroll
   down through the categories/device list and select the sensor — it may be listed by name/model,
   under a general "Sensor" category, or show up as an already-detected nearby device to confirm.
   (Some app versions instead want you to open the **gateway's own device card** first and add the
   sensor from an "Add Sub-Device" option there — if "Add Device" at the top level doesn't find it,
   try that route instead.)
3. Follow the on-screen steps to finish pairing — the app finds the nearby gateway on its own and
   links the sensor to it; you don't pick the gateway by hand.
4. Give it a name in the app (e.g. "Ball Python Tub — Tuya Probe") — this is just for your own
   reference in Tuya Smart, separate from whatever label you give it in HerpMonitor later.
5. Confirm you can see live temperature and humidity readings on the sensor's card in the app before
   moving on — if you can't, the pairing didn't fully finish; repeat from step 2.

---

## 4. Adding It to HerpMonitor

Since HerpMonitor can't read this sensor automatically (see below), you add it as a **Manual
Sensor** — the same kind you'd use for a handheld thermometer or test strip, just one you happen to
also be able to check remotely in the Tuya Smart app.

1. On HerpMonitor's Admin page, go to the enclosure (or Room) this sensor is actually monitoring.
2. In the **"Add Sensor"** form, set **Tracking Mode** to **Manual**.
3. Give it a label (e.g. "Tuya probe — water" or "Tuya ambient — tub air", especially useful since
   this device reports two separate readings — see the note below).
4. Set a **target range** (min and max) for whichever it measures — required for a Manual Sensor,
   since there'd otherwise be nothing to judge a hand-logged reading against.
5. Click **Create**.

**About the two readings (ambient + probe):** this device reports its own ambient temperature/
humidity *and* a separate temperature from the probe cable — two different physical locations (e.g.
the air in the room vs. the water in a tank). HerpMonitor's Manual Sensor is one label with one
target range at a time, so if you want to track both, add it as **two separate Manual Sensors** (one
labeled for the ambient reading, one for the probe), even though they both come from the same
physical device.

---

## 5. Using It Day to Day

Whenever you check the sensor in the Tuya Smart app, open HerpMonitor's dashboard and use the
**"Log Reading"** form that appears under that Manual Sensor's row — type in what the Tuya app just
showed you, and click it. There's a date/time box if you're logging a reading from a bit earlier
rather than right now.

This is the same as any other Manual Sensor — nothing updates by itself, so how current the reading
is on HerpMonitor's dashboard depends entirely on how often you copy it over.

---

## What HerpMonitor Can and Can't Do With It

| | Works today |
|---|---|
| Live readings, alerts, "weather function," Alexa | ✅ Yes — entirely inside the Tuya Smart app, independent of HerpMonitor |
| Automatic readings on HerpMonitor's dashboard | ❌ Not yet — HerpMonitor has no plugin that understands this device's data, only Govee sensors and Gosund/Tuya *plugs* today |
| Hand-logged readings, target-range coloring, care history alongside this enclosure's other data | ✅ Yes — via Manual Sensor, as above |
| Send Alert push notifications if a reading goes out of range | ❌ Not yet — Send Alert only watches Smart (automatic) Sensors; a Manual Sensor has nothing automatic to watch |

Automatic support for this device is a known, tracked gap — it's on the list, not forgotten — but
worth being upfront that it's a harder one than it might sound. The Gosund plugs HerpMonitor already
reads automatically talk directly over your home network, so HerpMonitor's software can just ask
them for their status. This sensor doesn't talk to your network at all — everything it reports has
to pass through your Zigbee gateway first, and gateways generally don't expose that sub-device data
on the local network the same simple way; getting it usually means going through Tuya's cloud
service instead (an account, an internet connection, and Tuya's own servers involved every time,
rather than everything happening locally between your own devices). That's a meaningfully bigger
lift than the Govee/Gosund support already built, so there's no promised timeline — but nothing
about setting it up as a Manual Sensor now would need to be redone later if it does land; it would
just start updating on its own instead of by hand.
