# Reptile Husbandry App — Project Plan & Decision Tracker

*Living document. Updated each session — items get added, removed, resolved, or revisited here as decisions firm up.*

**Last updated:** 2026-09-22 (Session 5)

**North star (confirmed):** Not optimizing for max revenue. Free, fully-functional, unlimited local self-hosted core for everyone; one small optional paid tier to cover hosting costs. Model: Home Assistant / Nabu Casa.

---

## Status legend
- ✅ **Decided** — locked in, build against this
- 🟡 **Recommended, not confirmed** — has a strong recommendation on record, needs your sign-off
- ⚪ **Open** — not yet discussed in depth
- 🔵 **In progress** — actively being worked

---

## 1. Business Model & Pricing — ✅ Decided
- Free local core, unlimited animals, no feature gating on the core app.
- One paid subscription: "From Anywhere" remote web access, **$3–5/mo or $29–39/yr**.
- Stage 2 (later): metered add-ons (cloud image/video push, cloud backup) — capped, not bundled.
- Stage 3 (later, optional): lifetime "supporter" license (~$60–99), donation/tip-jar path.
- Framing: "funds the project / covers infrastructure," never "unlocks features."
- Full research: `Pricing_Strategy_for_an_Open-Source_Reptile_Husbandry_App...md` (project file)
- Cash flow model: `Reptile App Cash Flow Model.xlsx` (project file) — default scenario breakeven month 5 (operating) / month 19 (cumulative)

**Next touch:** revisit only if conversion/cost thresholds in the pricing doc get triggered post-launch, or if a second pricing tier is modeled.

---

## 2. Licensing — ✅ Decided: AGPL-3.0-or-later
- **Decision (2026-10-16):** AGPL-3.0-or-later for the core app. Prevents a well-funded competitor from forking the free core into a closed hosted product. Earlier releases shipped under MIT and stay MIT for anyone who already has them.
- **Structure:** open-core — AGPL core + a small closed relay/mobile-push service sold as the subscription (same shape as Nabu Casa ↔ Home Assistant).
- **Still open:** whether to require a CLA; a short legal review of how the closed relay interacts with the AGPL core.

**Next touch:** dedicated session — needs your sign-off before any public repo goes up.

---

## 3. Remote Access — Architecture & Security — ⚪ Open (pricing done, implementation not)
- **Decided:** priced at $3–5/mo, positioned as the one paid feature.
- **Not decided:** how it's actually built.
  - Options flagged previously: Tailscale/Headscale-style mesh tunnel vs. reverse proxy (e.g. Caddy/Traefik + your own relay) vs. fully custom relay service.
  - Security/auth model for exposing a local server to the internet (this is the part that most needs care — auth, TLS, rate limiting, abuse prevention).
- **Depends on:** licensing decision (if the relay is the closed paid component, its design is central to the whole business model).
- **Scope narrowed (2026-09-22):** per Item 7a, the relay only carries reads and alerts — no device commands. Much smaller security surface. (Jira: RHA-6, linked to RHA-45)

**Next touch:** architecture session, likely paired with the diagram (item 5).

---

## 4. Camera Integration — ✅ Decided (strategy), ⚪ Open (build details)
- ONVIF for discovery + RTSP for streaming, brand-agnostic baseline.
- Frigate (MIT, MQTT-based) integrated as optional companion, not rebuilt from scratch.
- Community-maintained compatibility list for cameras rather than promising universal ONVIF support.
- **Open:** how Frigate's optional presence affects install complexity/UX for non-technical users; whether camera support ships at launch or later (see item 8, phasing).

---

## 5. System Architecture Diagram — ⚪ Open (flagged twice, still not done)
- Needs to tie together: local server, MQTT broker, ESP32 BLE proxies (Govee/Tuya sensor bridge), ONVIF cameras, Frigate companion, and the optional remote-access relay.
- Best done alongside item 3, once remote-access architecture has at least a candidate shape.

---

## 6. Data Model / Schema — ⚪ Open
- Rooms / animals / sensors / cameras — relationships and fields not yet designed.
- Depends loosely on item 8 (phasing) — e.g., whether breeding records, multi-user households, or shared/public profiles are in v1.

---

## 7. Hardware Questions — 🔵 Up next (this session)
- Not yet scoped. Likely covers: what hardware to recommend/support (ESP32 boards, sensor brands, camera brands), reference hardware kit vs. BYO, and how hardware choices interact with the BLE proxy pattern from prior sessions.

### 7a. Smart Plug Control — ✅ Decided (2026-09-22): monitor/track only
- **Decision:** The app does **not** send on/off or mode commands to plugs in v1. Plugs are monitored and tracked only (state, wattage, activity log, reminders, alerts).
- **Why:** asymmetric failure modes (a broken monitor = missing graph; broken control = dead animal or fire); smart plugs are a worse substitute for dedicated thermostats (Herpstat/VE/Inkbird); read-only remote access is a far smaller attack surface; lower liability for a hosted service; Home Assistant users can automate via MQTT and own that risk.
- **What changes:** Plug "modes" from the Plug data model become *expected behavior* used for anomaly alerts, not commands. Prototype control paths get removed.
- **New value from read-only:** wattage-drop burnout detection (bulb/CHE dies → alert before temp falls); plug-state vs. expected-behavior alerts cross-checked with sensors.
- **Revisit:** local-only manual toggles (no automation, no remote path) may be reconsidered post-launch.
- **Jira:** RHA-45 (decision), RHA-46 (rework plug modes), RHA-47 (strip write paths from prototype), RHA-48 (wattage burnout detection), RHA-49 (anomaly alerts), RHA-50 (MQTT read-only export), RHA-51 (v2 revisit).

---

## 8. Tech Stack — ⚪ Open
- Not yet chosen. Depends on data model, remote-access architecture, and whether mobile app is v1 or later.

---

## 9. Feature Phasing — ⚪ Open
- Environment monitoring (sensors) vs. animal records vs. cameras vs. breeding tools — order not yet set.
- A working prototype already exists locally (per prior session) — worth auditing what it already covers before phasing the rest.

---

## 10. Naming / Branding — ✅ Decided (2026-09-23)
- **Company / primary site:** CaskAbove (CaskAbove.com)
- **Full product name:** CaskAbove Husbandry Tracker
- **Short name (in-app):** Husbandry Tracker (e.g. "Husbandry Tracker Dashboard")
- **Website/marketing line:** Cask Above brings you the "Husbandry Tracker"
- **Retired:** "Herp Tracker" (collides with the existing competitor app HerpTracker) and "HerpMonitor" (former in-app label, renamed 2026-09-27 — see ADR 0020).
- **Open:** "CaskAbove" vs. "Cask Above" styling — pick one and use it everywhere.
- **Jira:** RHA-10 (decision + usage rules), RHA-52 (rename in UI/docs/repo).

---

## 11. Go-to-Market — 🟡 Recommended, not confirmed
- Organic-first recommended: Reddit (r/reptiles + species subs), FB husbandry groups, Discord, GitHub/HN. Paid ads only as a modest ~$300–500 test if desired.
- **Not committed:** timing of marketing push relative to launch/licensing/website readiness.

---

## 12. Legal / Business Formation — ⚪ Open
- LLC not yet formed (cost-estimated only: ~$150–700 lean bootstrap, up to $1,400–5,000 polished).
- ToS/privacy policy templates not sourced.
- Interacts with licensing (item 2) and remote-access relay (item 3) — a hosted paid service raises different liability/ToS needs than pure open-source distribution.
- Liability reduced by Item 7a (no device control), but ToS should still state the app is a monitoring tool and not a substitute for a thermostat.

---

## 13. Website — ⚪ Open
- Not built. Cost-estimated only (~$10–40/mo recurring infra to start).

---

## Dependency notes (for sequencing future sessions)
- **Licensing (2)** should probably land before the repo goes public, but doesn't block architecture work.
- **Remote-access architecture (3)** and **the diagram (5)** are naturally paired.
- **Data model (6)** and **tech stack (8)** and **phasing (9)** are tightly coupled — likely a single combined session.
- **Legal (12)** and **website (13)** are late-stage and don't need attention until closer to launch.

---

## Session log
- **Session 3:** Pricing strategy finalized, cash flow model built, camera strategy set, licensing recommendation made (unconfirmed), startup costs estimated, marketing approach recommended (uncommitted).
- **Session 4:** Plan/tracker document created. Moving into hardware questions.
- **Session 5 (current):** Decided smart plugs are monitor/track only (Item 7a). Jira tickets RHA-45 to RHA-51 created and linked to RHA-6, RHA-12, RHA-33. Naming decided: CaskAbove Husbandry Tracker (Item 10; RHA-10 updated, RHA-52 created).
