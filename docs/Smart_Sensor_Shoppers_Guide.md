# Smart Temp/Humidity Sensor Shopper's Guide

*A quick guide to picking the right sensor setup before you buy — for anyone new to smart temp/humidity sensors.*

---

## First, a heads-up: "Tuya" isn't a brand, it's a backend

You'll see "Tuya" everywhere on these listings, but it's not one company selling one product line — it's a **cloud platform that hundreds of different brands build their devices on top of**. That matters for two reasons:

1. **A device can be "Tuya-powered" and still not be Tuya-compatible in the way you'd expect.** Some brands white-label the Tuya backend but lock their device to their *own* app and account — you can't just add it inside the generic Tuya Smart app, even though the underlying tech is the same. Watch for this: if a listing has its own named app in the instructions (not "Tuya Smart" or "Smart Life"), assume you'll need to create a separate account with that brand, with its own login and password, even if it's Tuya under the hood.
2. **Ecosystem compatibility is really about the app/account, not the radio protocol.** Two "Zigbee 3.0" devices from different brands can still fail to talk to each other if their apps/clouds don't match (see the Aqara note below).

## What Husbandry Tracker already reads automatically today

- **Govee sensors** — supported now, automatic.
- **Gosund plugs** (Tuya-based) — supported now, automatic.

## What's not automatic yet, but is on the roadmap

- **Generic Tuya-app devices** (temp/humidity sensors, other Tuya plug brands) — not read automatically yet; log them as Manual Sensors for now. This is a known, tracked gap, not forgotten — plugin support is planned, and any Tuya device you buy today will keep working as a Manual Sensor, then start updating on its own once support lands. Nothing you set up now needs to be redone later.

**Practical effect while you're buying today:** any Govee or Gosund device you buy plugs in with zero manual logging, starting now. A Tuya-app device you buy today logs by hand for a while, then goes automatic later — you're not wasting money by buying it early, just trading a bit of manual work now for a device that'll "graduate" to automatic when the plugin ships.

---

## Before you shop: answer these 4 questions

### 1. Which ecosystem does it actually run on — and do you care about automatic readings *now* or are you OK waiting?

- Want it hands-off starting **today**? → stick to **Govee** (sensors) or **Gosund** (plugs) — the only two with automatic support right now.
- OK hand-logging for now, in exchange for more sensor/brand choice? → **Tuya-app devices** (open field, huge selection, cheaper competition) are fine — you'll just use a Manual Sensor until the plugin arrives.
- Considering some other named brand? → Check whether its app is literally "Tuya Smart"/"Smart Life" (roadmap item, will eventually be automatic) or its own separate branded app (see the account/password section below — likely never automatic unless Husbandry Tracker builds a dedicated plugin for that specific brand).

### 2. Will you be adding more animals/sensors down the road?

This decides whether a Zigbee gateway is worth the extra money (this applies within the Tuya-app world specifically — Govee and Gosund don't use gateways).

- **Just one animal, no plans to expand →** a WiFi-direct sensor alone is usually the better deal.
- **Multiple enclosures now, or planning to grow →** a Zigbee gateway starts to make sense, because **one gateway supports unlimited Zigbee sensors** added one at a time, usually cheaper per sensor than buying WiFi versions repeatedly.

**Rule of thumb:** 3+ sensors eventually → the gateway usually pays for itself. 1–2 → skip it.

### 3. Do you need to *control* something, or just *monitor* it?

- **Monitor-only sensors** — just report readings to your phone (and to Husbandry Tracker, automatically or by hand depending on brand — see above).
- **Plug/relay controllers** — a sensor combined with a smart outlet that can automatically turn a heat mat, humidifier, or fan on/off. Gosund's automatic plug support is specifically this category.

**If you already have a thermostat** (like a Zoo Med ReptiTemp) controlling your heat source, you likely just want a **monitor-only** sensor.

**If you want the app to actually switch equipment on/off**, look for "controller"/"relay"/"switch" in the listing.

### 4. Do you want a screen on the device itself, or phone-only?

Doesn't affect compatibility — just personal preference for glancing at the tank vs. always checking the app.

---

## WiFi vs. Zigbee (within the Tuya-app world)

| | **WiFi-direct** | **Zigbee + Gateway** |
|---|---|---|
| **Upfront cost (1 sensor)** | ~$10–20, nothing else needed | ~$35–45 (gateway + first sensor) |
| **Cost per additional sensor** | Full price each time (~$10–20) | Cheaper per sensor after the gateway (~$8–20) |
| **Setup steps** | Connect once, done | Set up gateway once, then pair each sensor to it |
| **Best for** | 1–2 sensors, simple setup | 3+ sensors, growing collection |
| **Uses your WiFi** | Yes, every sensor | No, only the gateway does |
| **Extra point of failure** | None | Yes — gateway drops, everything on it drops |
| **2.4GHz-only requirement** | Yes, the sensor | Yes, but only the gateway — sensors don't care |

---

## What is NOT compatible — and why

### ❌ Zoo Med smart devices
There aren't any. Zoo Med's ReptiTemp thermostats/gauges are standalone digital/analog devices — no app, no cloud, nothing to connect. Not a compatibility gap, just nothing to connect to.

### ❌ REPTI ZOO "Smart WIFI" line
Looks Tuya-compatible, isn't. Runs on its own separate proprietary cloud/app, not Tuya's — won't show up in Tuya Smart no matter how you try to add it. Treat it as a fully separate ecosystem.

### ⚠️ Any device with its own named brand app (not "Tuya Smart"/"Smart Life")
This is the "branded account" trap. Some devices are Tuya-powered underneath but require you to sign up for *that brand's own account* — with its own password — to use the device at all. That account boundary means Husbandry Tracker can't reach the device's data without a plugin built specifically for that brand, even if it's technically running on Tuya's infrastructure. Practically: if setup asks you to create an account under a brand name you don't recognize (not Tuya, not Govee, not Gosund), assume it's its own island for now.

### ❌ Mixing hub brands (Zigbee specifically)
A Zigbee sensor only pairs with a Tuya gateway if it's a **Tuya-protocol** Zigbee device. **Aqara**, for example, makes Zigbee 3.0 sensors that need *Aqara's own* hub — "Zigbee 3.0" on the box doesn't guarantee cross-brand compatibility. When buying a Zigbee sensor for a Tuya gateway, confirm the listing says "Tuya" or "Smart Life app," not just "Zigbee 3.0."

### ❌ 5GHz WiFi
Neither WiFi-direct sensors nor Tuya gateways can join a 5GHz network — only 2.4GHz. If your router broadcasts one combined network name, you may need to temporarily split the bands during setup.

---

## FAQ: Does the gateway (or my computer) need to stay on all the time?

**The gateway: yes, always on.** It's the *only* path a Zigbee sensor has to reach WiFi or the internet at all — if it loses power, every sensor connected to it goes dark immediately, even inside the Tuya app itself, completely separate from Husbandry Tracker. Treat it like your router or modem: plug it in somewhere you never unplug.

**Your Husbandry Tracker computer: no — gateway or not.** This is independent of whether you have a gateway at all:
- **Today (Manual Sensor logging):** it only needs to be on at the moment you sit down to type in a reading. Off the rest of the time, no data is "missed" — you're just choosing when to transcribe.
- **Once automatic plugin support ships:** it would only need to be on when it checks in to pull fresh data. The cloud (Tuya's, Govee's, whichever) holds the history in between, so your computer being off overnight wouldn't lose readings — it'd just catch up next time it's on.

**So the two "always on" requirements don't transfer to each other.** Having a gateway doesn't make your computer need to run 24/7, and *not* having a gateway (WiFi-direct sensors) doesn't add any always-on burden either — your computer's schedule is the same either way. The gateway's always-on rule exists purely because it's the sensor's only lifeline to the outside world, which is a Zigbee-specific quirk, not a general "smart sensor" rule.

---

## Quick picks

- **"I want automatic readings in Husbandry Tracker starting today, simplest option"** → Govee sensor (monitoring) or Gosund plug (if you need on/off control).
- **"I'm OK hand-logging for now, but want more sensor choice/lower cost"** → Tuya-app WiFi sensor, monitor-only. ~$10–15.
- **"I have several tanks and plan to add more"** → Tuya Zigbee gateway (~$20–25) + Zigbee sensors per tank (~$10–20 each) — still Manual Sensors in Husbandry Tracker for now, automatic later.
- **"I want the app to turn my heat mat on/off automatically, today"** → Gosund relay/plug.
- **"I own Zoo Med or REPTI ZOO smart gear already"** → Won't integrate with any of the above. Keep it separate, or replace with a Govee/Gosund/Tuya product if you want one unified app.
- **"A product's setup wants me to create some other brand's account"** → Treat it as its own island unless/until Husbandry Tracker lists a plugin for that specific brand.
