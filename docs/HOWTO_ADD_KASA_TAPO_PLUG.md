# How To: Add a Kasa or Tapo Plug

This covers TP-Link **Kasa** and **Tapo** smart plugs, power strips, and wall switches: the kind you
plug a heat mat, basking bulb, fogger, or light into so Husbandry Tracker can see whether it's on,
turn it on or off, and (on some models) show how much power it's drawing.

**Why pick these over Gosund/Tuya plugs:** Husbandry Tracker finds Kasa and Tapo plugs directly on
your Wi-Fi. There's no developer account to create, and no cloud trial that runs out (see the
Gosund how-to's [The free trial runs out](HOWTO_ADD_GOSUND_PLUG.md#the-free-trial-runs-out)).

> **New:** support for these plugs was added before anyone had tested it on real hardware. If
> something doesn't work, note the plug's exact model (on the label, e.g. "KP115" or "P110") and
> what you saw.

**Contents**
1. [What You Need](#1-what-you-need)
2. [Set the Plug Up in the Kasa or Tapo App](#2-set-the-plug-up-in-the-kasa-or-tapo-app)
3. [Turn On the Kasa / Tapo Plugin](#3-turn-on-the-kasa--tapo-plugin)
4. [Scan and Name Your Plugs](#4-scan-and-name-your-plugs)
5. [Add Each One as a Plug](#5-add-each-one-as-a-plug)
6. [Power Strips](#6-power-strips)
7. [If Something Goes Wrong](#7-if-something-goes-wrong)

---

## 1. What You Need

- **The plug**, plugged into power. Models with an **energy meter** also report watts, volts, and
  amps: for example Kasa **KP115**, **EP25**, **HS300** (each outlet), and Tapo **P110** and
  **P115**. Basic models like the Kasa **EP10** or Tapo **P100** report on/off only.
- **The Kasa or Tapo app** on your phone, whichever one the box tells you to use.
- **The plug and this computer on the same Wi-Fi network.** Not a guest network, and not a
  separate network your router keeps apart. Like most smart plugs, these join 2.4 GHz Wi-Fi only.
- **Your TP-Link login** (the email and password for that app), for newer Kasa plugs and all Tapo
  plugs. Older Kasa plugs don't need it.

## 2. Set the Plug Up in the Kasa or Tapo App

Follow the app's own steps to add the plug to your Wi-Fi, and check you can switch it from the
app. Husbandry Tracker can't do this first-time Wi-Fi setup itself.

## 3. Turn On the Kasa / Tapo Plugin

1. Go to **Admin**, find the **Plugins** card, and click **Settings** next to **TP-Link Kasa / Tapo
   Smart Plugs**.
2. Click **Activate**.
3. Under **Settings**, enter your **TP-Link email** and **TP-Link password** and click **Save**.
   Skip this if all your plugs are older Kasa models. The password is only ever sent to your own
   plugs, on your own network, and it's never shown again once saved.

## 4. Scan and Name Your Plugs

On the same Settings page, under **Devices**, click **Find plugs on my network**. After about five
seconds you'll see every Kasa and Tapo plug it found, with its model, address, and whether it's on.
Type a name you'll recognise for each ("Basking lamp", "Fogger") and click **Save**.

If it says some devices **need your TP-Link login**, enter it under Settings (step 3) and scan
again.

## 5. Add Each One as a Plug

1. On the **Add Plug** form, set **Tracking Mode** to **Smart**.
2. Set **Plug type** to **TP-Link Kasa / Tapo**.
3. Pick the plug from **Named devices**. This fills in its **MAC address**, **Outlet**, and
   **LAN IP**, and uses its name as the Label. You can also click **Discover Devices** right there
   instead.
4. Fill in **Purpose**, **Belongs to**, and the rest as for any Plug, then click **Create**.

You can leave **LAN IP** blank. Husbandry Tracker finds the plug by its MAC address, including after
your router gives it a new address.

**Already have a Manual Plug for this?** Open its **Edit** page, switch **Tracking Mode** to
**Smart** and **Plug type** to **TP-Link Kasa / Tapo**, and fill it in the same way.

## 6. Power Strips

Each outlet of a strip (like the Kasa **HS300** or **KP303**) is its own Plug, with the same MAC
address and a different **Outlet** number (1, 2, 3...), counted the way the strip reports them. A
scan lists each outlet separately, so picking one from **Named devices** fills in the right number.
(The Plug Group feature for Tuya strips isn't used for Kasa/Tapo.)

## 7. If Something Goes Wrong

- **The scan finds nothing:** check the plug works in its app, and that it's on the same Wi-Fi
  network as this computer, not a guest network.
- **"Need your TP-Link login" or "refused the TP-Link login":** re-enter the email and password
  you use in the Kasa or Tapo app on the Plugin's Settings page.
- **It worked, then stopped after the plug updated itself:** TP-Link sometimes changes how these
  plugs log in. Updating Husbandry Tracker usually brings the fix. The plug's own log
  (`data/logs/kasa.log`) says what went wrong.
- **The Plug shows Unreachable:** the plug is off, out of Wi-Fi range, or on another network. It
  reconnects on its own once it's back.
