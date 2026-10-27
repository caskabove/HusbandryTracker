# How To: Add a Gosund Smart Plug

This covers Gosund WiFi smart plugs — the kind you plug a heat mat, basking bulb, fan, or light
into so Husbandry Tracker can see whether it's on or off, automatically. These plugs run on Tuya's
technology under the hood (same company behind the Tuya Smart app), but are set up through a
different, older app: **Smart Life**.

**Read this first:** unlike the Govee sensor or the Tuya Zigbee sensor, this device connects
directly to your home WiFi — no Bluetooth, no gateway/hub needed. Getting Husbandry Tracker talking to
it needs one extra step beyond just pairing it in the app — linking a free Tuya developer account
(see [Get Tuya Developer Credentials](#3-get-tuya-developer-credentials) below) — but once that's
done **once**, every plug after it is just a button click; no Command Prompt needed.

**Contents**
1. [What You Need](#1-what-you-need)
2. [Add Tuya Device (Pairing the Plug in Smart Life)](#2-add-tuya-device-pairing-the-plug-in-smart-life)
3. [Get Tuya Developer Credentials](#3-get-tuya-developer-credentials)
4. [Confirming the On/Off Switch Key](#4-confirming-the-onoff-switch-key)
5. [Adding It to Husbandry Tracker](#5-adding-it-to-husbandry-tracker)
6. [Using It Day to Day](#6-using-it-day-to-day)

---

## 1. What You Need

- **The Gosund plug itself**, plugged into power.
- **The Smart Life app** on your phone — free, from your phone's app store (search "Smart Life").
  **Not Google Home** — Google Home has no way to hand Husbandry Tracker the credentials it needs, even
  though it can also control the same plug. Gosund plugs must be set up in Smart Life (or Tuya
  Smart — either works for this step) for the rest of this guide to work.
- **Your phone connected to 2.4GHz WiFi during pairing** — most inexpensive smart plugs, this one
  included, can only join a 2.4GHz network, not 5GHz. If your router broadcasts both under the same
  name, this is the most common reason pairing silently fails — see the same callout in the [Tuya
  Zigbee sensor how-to](HOWTO_TUYA_TEMP_HUMIDITY_PROBE_SENSOR.md#1-what-you-need) for how to check.
- **A free Tuya IoT developer account** (step 3 below walks through creating one) — a one-time
  account-linking step on Tuya's own website, done once no matter how many plugs you add
  afterward. No Python, no Command Prompt — Husbandry Tracker talks to Tuya's cloud for you once
  you've saved your Access ID/Secret (see step 3).

---

## 2. Add Tuya Device (Pairing the Plug in Smart Life)

1. Open the **Smart Life** app and create a free account if you haven't already.
2. Tap **Add Device**. Scroll down through the categories/device list and select the plug (often
   listed under "Electrical" → "Socket," or it may auto-detect nearby).
3. Follow the on-screen pairing steps — this is where your phone's 2.4GHz WiFi connection matters
   (see the callout above); you'll be asked for your WiFi password so the plug itself can join your
   network directly.
4. Give it a name in the app — this is just for your own reference in Smart Life, separate from
   whatever label you give it in Husbandry Tracker later.
5. Confirm you can turn it on/off from the app before moving on.

*(If any of these exact screens or button names don't match what you actually see, let me know — this
section is written from how Tuya's standard pairing flow normally works, not a verified run-through,
and I'd rather fix it than leave it wrong.)*

---

## 3. Get Tuya Developer Credentials

Every Gosund plug has a **device ID** and **local key** — think of them like a name and password
Husbandry Tracker needs to talk to the plug directly over your WiFi, without going through Tuya's cloud
every time. Unlike a Govee sensor's ID, these can't be found with a simple scan; getting them
requires linking a free Tuya developer account to the same account you just used in Smart Life.
That account-linking step happens entirely on Tuya's own website and can't be skipped — but it's a
**one-time** setup, not something you repeat per plug.

1. Go to [iot.tuya.com](https://iot.tuya.com) and create a free account if you don't already have
   one.
2. Create a "Cloud" project, then link it to your Smart Life account — this step usually involves
   scanning a QR code with your phone (in the Smart Life app) to prove it's really your account.
3. The project's page shows an **Access ID** and **Access Secret**. In Husbandry Tracker, go to the
   Plugs and Sensors page's **Tuya Cloud Credentials** card, paste both in, pick your API Region (Americas,
   Europe, China, or India — matching where your Tuya Cloud project was created), and click **Save**.

**This step's website screens belong to Tuya, not Husbandry Tracker** — their exact wording/layout can
change over time and isn't something this guide can promise pixel-for-pixel. If you get stuck partway
through, tell me exactly what screen/prompt you're on and I'll help from there.

Once saved, every Add Plug and Add Plug Group form gets a **Discover Devices** button: click it, and
Husbandry Tracker asks Tuya's cloud for every device linked to that account, listing each by name —
click the one you mean and it fills in the device ID and local key for you. No Command Prompt, no
`devices.json` file to protect — the Access Secret is saved once, server-side, and is never shown
again once you've entered it.

---

## 4. Confirming the On/Off Switch Key

The Discover Devices button already fills in a **best guess** at the on/off switch key (most
single-outlet plugs use "1"), but it's a guess, not a guarantee — some models use a different DPS
layout. Worth a quick check before trusting it, using a small script that (unlike Discover) does
need a one-time Python install: [Python itself](https://www.python.org/downloads/) (check "Add
python.exe to PATH" during install) plus a download or `git clone` of the [Husbandry Tracker
repository](https://github.com/caskabove/HusbandryTracker) — anywhere on your computer, just to
borrow its `tools/` folder and `requirements.txt`. Then, in a Command Prompt in that folder:

```
pip install -r requirements.txt
python tools\tuya_probe.py <device_id> <local_key> --ip <ip_from_discover>
```

While this is running, toggle the plug from the Smart Life app and confirm which key flips in the
output. If it's not what Discover filled in, enter the correct number instead in the next step. If
it matches, this whole step is skippable.

Leave the IP address blank later in Husbandry Tracker unless a plug keeps failing to connect.

---

## 5. Adding It to Husbandry Tracker

Unlike Sensors (added from the Enclosure/Room they belong to), Plugs are added from Husbandry Tracker's
**main Admin page** (`/admin`), in its own **"Plugs"** card.

1. Fill out the **"Add Plug"** form: **Tracking Mode: Smart**, a label (e.g. "UTH", "basking bulb"),
   and a **Purpose** (heat/light/cooling/etc.).
2. **Belongs to**: check the Enclosure(s) it serves (almost always just one — check more than one
   only if a single physical plug controls several tubs at once), or pick a Room instead for a
   genuinely room-wide fixture.
3. Click **Discover Devices**, then click this plug from the list — that fills in the **device ID**
   and **local key** (and takes a best guess at Outlet/DPS key — see step 4 above) for you.
4. Double-check **Outlet/DPS key** is `1` (or whatever step 4 above confirmed) unless this is a
   multi-outlet power strip (which needs one row here per outlet actually in use — `2`, `3`, or `7`
   for a USB port — all sharing the same device ID/local key).
5. Click **Create**.

---

## 6. Using It Day to Day

Nothing to do — Husbandry Tracker polls this plug directly over your WiFi every few seconds and updates
its on/off status automatically, no app needed. The **Command** buttons on its pill (dashboard,
Room, or Enclosure page) let you turn it on/off manually right from Husbandry Tracker — useful for reacting
quickly to an alert. The **Schedules** card shows its inferred on-time once Husbandry Tracker has watched
it through at least one full on/off cycle; until then it'll say "no schedule data yet," which is
expected, not an error.
