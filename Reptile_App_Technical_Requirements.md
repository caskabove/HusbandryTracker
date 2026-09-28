# Reptile Husbandry App — Technical Requirements & Roadmap

**Purpose of this document:** This is the single source-of-truth handoff for whoever builds the app — one place where current (v1) requirements, the decision tracker, and known future direction live side by side, so early build decisions don't have to be unwound later. Every requirement is tagged with a status; every item in "Build Strategy Implications" flags a decision that is cheap to make now and expensive to retrofit.

As of v2 (2026-08-28) this document also absorbs the former `Reptile_App_Project_Plan.md` decision tracker — §8 (Build Status), §9 (Open Decisions & Work Tracker) and §10 (Session Log) are the merged-in content. The Project Plan file is now a stub pointing here.

**Status:** Living document, version 2 — reflects decisions through Session 5 (2026-08-25) plus the 2026-08-28 alignment review and Project-Plan merge.

---

## 1. Product Vision & Non-Negotiables

- **North star:** A free, fully-functional, unlimited, self-hosted local core for every user. One small optional paid subscription for remote ("from anywhere") access, which funds hosting/development. Model: Home Assistant / Nabu Casa. Not optimizing for maximum revenue.
- **Non-negotiable constraints** (these override convenience decisions anywhere else in this doc):
  1. The local core must **never** require internet access, an account, or a subscription to be fully functional.
  2. The local core must **never** gate by animal count, feature count, or usage. (This is the single most common complaint against every existing competitor — see competitive research doc. Gating the core is a product failure, not a pricing lever.)
  3. Paid tiers are **per household/instance**, never per-seat or per-animal.
  4. User data (husbandry records, images, sensor history) is not held hostage — must be exportable in an open format at any time, paid or not.

These four constraints should be treated as acceptance criteria for every future feature, not just v1.

---

## 2. Current Requirements (v1 — build now)

### 2.1 Core Application
- Husbandry tracking: animals, enclosures/rooms, environment sensors, feeding/care logs.
- Runs entirely locally; no cloud dependency for core function.
- Web-based local UI. Stack is now chosen (see §9.8): Python + FastAPI + Jinja2 + SQLite, must run on modest local hardware (Raspberry Pi class).

### 2.2 Environment Monitoring
- **Superseded by ADR 0013.** The original v1 spec here was "sensor ingestion via MQTT broker" + an "ESP32-based BLE proxy pattern for bridging BLE sensors (Govee/Tuya-class) onto the local network." Neither was built.
- **Current design:** each vendor/protocol integration is an independent **Plugin** process that talks to core only through JSON files — a Registry export (core → plugin: what to watch) and an Inbox (plugin → core: what was observed), drained by an **Ingest** process that validates against `schemas/plugin_event.schema.json`. See ADR 0013 and CONTEXT.md (Plugin, Ingest, Plugin Event, Inbox, Registry).
- This is transport-agnostic by design: a future MQTT-bridge Plugin (or an ESP32 proxy feeding one) can sit behind Ingest later without Ingest changing. The MQTT/ESP32 idea is deferred, not foreclosed.
- Built-in Plugins today: Govee H5074/H5102 over BLE (`plugins/govee_ble/`, host process — BLE doesn't pass through Docker cleanly on Windows, see ADR 0001) and Tuya/Gosund plugs over LAN (`plugins/tuya_lan/`).
- Plugin follow-up decisions still open — see §9.14.

### 2.3 Camera Integration
- ONVIF for camera discovery, RTSP for streaming — brand-agnostic baseline.
- Frigate (MIT-licensed) integrated as an **optional** companion process, not rebuilt in-house.
- A community-maintained device compatibility list substitutes for a promise of universal support.

### 2.4 Remote Access (the one paid feature)
- "From Anywhere" subscription: $3–5/mo or $29–39/yr.
- 30-day free trial, no credit card required to start.
- Framing in all UI/marketing copy: "funds the project / covers infrastructure" — never "unlocks features."
- Underlying mechanism **not yet chosen** — candidates: Tailscale/Headscale-style mesh tunnel, reverse proxy + custom relay, fully custom relay service. This decision is architecture-critical — see §4.1 and §9.3.

### 2.5 Packaging & Install
- Primary near-term target: Docker Compose + one-line install script (handles Docker install + first-run prompts: admin password, timezone).
- Primary non-technical-user target: prebuilt Raspberry Pi OS image (HAOS-style), flashable via Raspberry Pi Imager/Balena Etcher.
- Secondary distribution: submission to self-hosted app-store platforms (Umbrel, CasaOS, TrueNAS SCALE Apps, Unraid Community Applications) once Docker packaging exists.
- **Note:** Docker is currently sidelined for local dev (ADR 0002) because the Govee BLE Plugin needs host Bluetooth access. The Tuya Plugin, Ingest and web all containerize fine; the Govee Plugin is the one host-process exception. This doesn't change the packaging *targets* above, but the Pi-image path is the cleaner fit given the BLE constraint.
- Full detail: see §4.4 and §9.7 (hardware).

### 2.6 Licensing (recommended, not yet confirmed — build should not assume final)
- Recommendation on record: AGPLv3 for the core app, open-core structure (AGPL/MIT core + closed relay/mobile-push component sold as the subscription).
- **Build implication:** code that will live in the closed relay component vs. the open core should be modularized as separably as possible from day one, regardless of final license choice — see §4.2.
- No `LICENSE` file exists yet — consistent with "not confirmed." See §9.2.

---

## 3. Future Requirements (roadmap — do not build yet, but design so these aren't blocked)

### Stage 2 (12–24 months post-launch, contingent on remote-access retention proving out)
- **Metered cloud image/video push add-on** — capped allowance (GB or clip-count), priced ~$2–4/mo, separate from the base subscription.
- **Cloud backup add-on** — a small (few-hundred-MB) snapshot bundled free into the remote-access subscription; larger retention sold as a metered upgrade.
- **Possible "Cloud" bundle** combining remote access + backup + media push at ~$5/mo.

### Stage 3 (later, optional)
- **Lifetime "supporter" license** (~$60–99) — grants cloud features for life, does not remove anything from non-payers. Pricing: ~15–20x the annual subscription rate. **Caution flagged in research:** lifetime pricing has caused repricing backlash elsewhere (Plex); if built, must be honored indefinitely once sold — do not build a lifetime SKU without a funding/liability plan for that commitment.
- **Donation/tip-jar path** for fully self-hosted users who never subscribe.

### Feature-level future candidates (not yet phased — see §9.9)
- Breeding records / breeding tools. (Schema note: `animal` has no lineage fields yet — see §9.6.)
- Multi-user households (shared access to one instance, multiple accounts/permissions).
- Public/shared animal profiles.
- Mobile app (unclear if v1 or later — see §4.3).

### Possible future hardware line
- Preconfigured hardware bundle (Pi or mini-PC, pre-flashed, ship-and-plug), Home Assistant Green/Yellow-style. Optional, contingent on demand; a hardware-business decision (inventory, shipping, support) as much as a technical one.

---

## 4. Build Strategy Implications — decisions that are cheap now, expensive later

This section exists because the whole point of this document is to prevent "unwinding." Anything listed here should be treated as an architectural decision point during initial build, even if the feature it enables is Stage 2/3.

### 4.1 Remote-access mechanism gates the entire business model
The paid subscription **is** the remote-access relay. Whatever is chosen here (mesh tunnel vs. reverse proxy vs. custom relay) determines:
- How auth, TLS, rate limiting, and abuse prevention are implemented (flagged as needing real care — see §9.3).
- Whether Stage 2's metered add-ons (image/video push, backup) can piggyback on the same transport or need a second one.
- How packaging (§4.4) bootstraps a device into the relay on first run.
**Build strategy implication:** don't hardcode the relay transport into core app logic. Put it behind an internal interface/service boundary so the transport can be swapped or extended (e.g., adding a media-push channel in Stage 2) without touching husbandry/data-model code.

### 4.2 Open-core split must be modularized from day one
Regardless of final license (AGPL/MIT/Apache), the plan is an open core + a closed, sold component (the relay). If the codebase isn't cleanly separated early, extracting the closed component later means a risky refactor under a licensing deadline.
**Build strategy implication:** structure the repo (or at least the module boundaries) as if the relay/subscription-gated code already lived in a separate package, even before the licensing decision is finalized. This costs little now and avoids a forced rewrite later. **Status:** not yet done — the repo has no relay/closed-component boundary. See §9.2.

### 4.3 Data model must anticipate multi-user and breeding records even if not built yet
§9.6 (data model/schema) is explicitly coupled to §9.9 (phasing) — whether breeding records, multi-user households, or shared profiles are in v1. Retrofitting multi-user permissions or breeding-record relationships onto a schema designed only for a single user/single animal-owner is a common source of painful migrations.
**Build strategy implication:** even if multi-user and breeding features are Stage 2+/not phased yet, the initial schema should not assume "one user, no ownership model." At minimum: model animals/rooms/sensors with an owner/household concept from the start, and leave room for animal-lineage relationships (parent/offspring) even if breeding tools aren't built yet. **Status:** neither is done yet — `db/schema.sql` has no `user`/household table and `animal` has no `dam_id`/`sire_id`. The schema is still actively growing, so this is still the cheap moment. See §9.6.

### 4.4 Packaging choice shapes onboarding, update mechanics, and remote-access bootstrap
Each packaging target (Docker Compose, Pi OS image, app-store package, desktop wrapper) implies different assumptions about:
- How the app receives updates (in-place update mechanism differs completely between a Docker container and a flashed OS image).
- How first-run configuration (including remote-access subscription signup) is presented to a non-technical user.
- Whether the app needs a "supervisor" layer (Home Assistant's actual innovation) to manage its own updates/add-ons independently of the OS.
**Build strategy implication:** decide early whether a supervisor/update-manager component is part of the core architecture (as in Home Assistant) or deferred. Retrofitting an update mechanism after users are already running unmanaged installs is difficult — this should be resolved alongside the Pi-image and Docker work, not after.

### 4.5 Camera/Frigate integration is a complexity and install-size lever
Because Frigate is an optional companion, its presence or absence changes install complexity meaningfully (extra process, its own MQTT broker dependency — Frigate is MQTT-based; note the sensor pipeline no longer uses MQTT, see §2.2 — plus GPU/CPU requirements for AI detection features per Frigate's own tiering).
**Build strategy implication:** camera support should be an installable/enable-able module, not baked into the base install, so the "Pi image" and "Docker Compose" packaging targets can each offer a lightweight base install with cameras as an explicit opt-in — keeping the non-technical-user path (§4.4) as simple as possible.

### 4.6 Usage caps and metering (Stage 2) require instrumentation now, even if unused
Stage 2's metered add-ons (cloud image/video push, backup) depend on the app being able to measure usage per household/instance (bandwidth, storage, clip counts) accurately enough to enforce a cap and bill against it.
**Build strategy implication:** build basic usage-metering hooks into the relay/subscription service now (even if no cap is enforced yet), rather than adding instrumentation retroactively once a Stage 2 add-on needs to bill against it.

### 4.7 Lifetime license (Stage 3) is a financial/legal commitment, not just a SKU
If ever built, a lifetime license is a promise to support that user's cloud access indefinitely at no further charge. This is a business/legal decision more than an engineering one, but engineering should not treat "lifetime" as just another price point in the billing table — it needs distinct handling (e.g., it cannot be tied to a recurring-subscription-cancellation code path).
**Build strategy implication:** billing/entitlement logic should distinguish "recurring subscription" from "perpetual entitlement" as separate concepts from the start of the billing system's design, even before a lifetime SKU is sold, so Stage 3 doesn't require re-architecting entitlements.

---

## 5. Explicit Non-Goals (v1 and beyond, unless revisited)

- No animal-count gating, ever, on the local core.
- No per-seat or per-animal pricing on any paid tier.
- No feature removed from non-paying users as a way to upsell (the subscription funds infrastructure, it doesn't unlock capability that free users are missing).
- No mandatory account/login to use the local core.
- No silent price increases without the "funds the project" framing being reinforced in the same communication (per the Plex/Nabu Casa contrast in the pricing research).

---

## 6. Success Metrics & Thresholds (from pricing research — inform, don't gate, build priorities)

These aren't build requirements per se, but the build should make it possible to measure them, since they're the triggers for future pricing/roadmap changes:
- **Free→paid conversion rate** — needs to be measurable per-household. If conversion exceeds ~5–8%, pricing may rise toward $5/mo or add tiers; below ~2%, cloud value prop needs strengthening before touching price.
- **Infrastructure cost per paying user vs. revenue** — if cost exceeds ~25–30% of that user's subscription revenue, caps tighten or media push moves to metered pricing immediately. Requires the usage-metering hooks in §4.6 to exist.
- Cash-flow model: `Reptile App Cash Flow Model.xlsx` (project file) — default scenario breakeven month 5 (operating) / month 19 (cumulative).

---

## 7. Open Dependencies Across This Document

- §4.1 (remote-access architecture) blocks finalizing §2.4 implementation and affects §4.4 (packaging) and §4.6 (metering).
- §4.2 (open-core modularization) depends on the licensing decision (§9.2) but should not wait on it to begin.
- §4.3 (data model) depends on feature phasing (§9.9) but should assume multi-user/breeding as a "don't block" requirement regardless of phasing order.
- §4.4 (packaging) is coupled to hardware recommendations (§9.7).
- §9.3 (remote-access architecture) and §9.5 (the system diagram) are naturally paired.
- §9.6 (data model), §9.8 (tech stack) and §9.9 (phasing) are tightly coupled — the first two are now largely resolved; phasing is the remaining open piece.
- §9.12 (legal) and §9.13 (website) are late-stage and don't need attention until closer to launch.

---

## 8. Build Status (as of 2026-08-28)

A snapshot of what is actually implemented, so the requirements above can be read against reality. This is the section that most often drifts — update it whenever a significant piece lands.

- **Architecture:** three independent processes — `web` (FastAPI/uvicorn), `ingest` (drains the Inbox, evaluates alerts), and one or more `plugins` — over a single SQLite database. ADR 0001, ADR 0013. Docker sidelined for dev (ADR 0002).
- **Tech stack:** Python, FastAPI, Jinja2 server-rendered templates, SQLite, `bleak` (BLE), `tinytuya` (LAN), `jsonschema` (Plugin Event validation). No ORM — hand-written SQL against `db/schema.sql`.
- **Data model:** mature. `db/schema.sql` covers room, enclosure, animal, plant, plant_health_log, sensor, plug (+ plug_enclosure, plug_last_seen), sensor_reading, plug_state_transition, plug_reading, care_event, sensor_alert_state, plug_alert_state, app_setting. 13 ADRs of decisions baked in. Terminology in `CONTEXT.md`.
- **Environment monitoring:** Plugin/Registry/Inbox/Ingest pipeline is live. Govee BLE and Tuya LAN plugins built. On-demand dashboard **Refresh** deliberately bypasses the pipeline (`web/govee_refresh.py`, ADR 0005).
- **Alerts:** state-machine alerting (normal → pending → alerting → resolved) with debounce, delivered via **ntfy** (ADR 0010). Out-of-range, zero-power-while-on, and unreachable conditions.
- **Dashboard & Admin UI:** built and running (see `docs/USER_GUIDE.md`) — enclosure/room panels, drag-and-drop room reassignment, target vs. detected schedule comparison, timer warnings, care-event logging, plant health.
- **Not yet built / in flight:**
  - Schedule *inference* logic (deriving "on ~08:00 for ~12h" from `plug_state_transition` history) — needs more real transition history first (`docs/PHASE1.md`).
  - Telemetry capture from plugs — machinery exists but no registered device exposes watts/volts/amps yet, and there's no per-plug config for which DPS key holds telemetry.
  - The Admin/web layer still carries vendor-specific field names (`mac_address`, `tuya_device_id`, …) behind shims (`web/admin_queries.py`), not yet fully migrated to the generic `plugin`/`external_id`/`plugin_config` model — see §9.14.
  - Python entity-schema layer — all 7 tracked entities built (`schemas/enums.py` + `sensor`/`plug`/`care_event`/`enclosure`/`room`/`animal`/`plant`), none wired into `web/admin_queries.py` yet, `plant_health_log` has no schema/ticket yet — see §9.15.
  - No user/household/auth model — see §9.6. `web/main.py` has an explicit "no auth" comment.
  - No animal lineage fields — see §9.6.
  - Camera integration: no code yet.

---

## 9. Open Decisions & Work Tracker

*Merged in from the former `Reptile_App_Project_Plan.md` on 2026-08-28, statuses updated to reality. Items get added, resolved, or revisited here as decisions firm up.*

**Status legend:** ✅ Decided (build against this) · ✔️ Built · 🟡 Recommended, not confirmed · ⚪ Open · 🔵 In progress

### 9.1 Business Model & Pricing — ✅ Decided
- Free local core, unlimited animals, no feature gating on the core app.
- One paid subscription: "From Anywhere" remote web access, **$3–5/mo or $29–39/yr** (see §2.4).
- Stage 2 (later): metered add-ons (cloud image/video push, cloud backup) — capped, not bundled (§3).
- Stage 3 (later, optional): lifetime "supporter" license (~$60–99), donation/tip-jar path (§3).
- Framing: "funds the project / covers infrastructure," never "unlocks features" (§5).
- Full research: `Pricing_Strategy_for_an_Open-Source_Reptile_Husbandry_App...md` (project file). Cash-flow model: see §6.
- **Next touch:** revisit only if conversion/cost thresholds in the pricing doc get triggered post-launch, or if a second pricing tier is modeled.

### 9.2 Licensing — 🟡 Recommended, not confirmed
- **Recommendation on record:** AGPLv3 for the core app. Prevents a well-funded competitor from forking the free core into a closed hosted product.
- **Structure:** open-core — AGPL/MIT core + a small closed relay/mobile-push service sold as the subscription (same shape as Nabu Casa ↔ Home Assistant).
- **Needs decision:** AGPLv3 vs. MIT vs. Apache 2.0 vs. other open-core split; whether to require a CLA.
- **Considerations when picked up:** contributor friction (AGPL can scare off some contributors), how it interacts legally with the closed relay component, the CLA question.
- **Blocks:** no `LICENSE` file and no public repo until this is signed off (§4.2 modularization can and should begin regardless).
- **Next touch:** dedicated session — needs sign-off before any public repo goes up.

### 9.3 Remote Access — Architecture & Security — ⚪ Open
- **Decided:** priced at $3–5/mo, positioned as the one paid feature (§2.4).
- **Not decided:** how it's built. Options: Tailscale/Headscale-style mesh tunnel vs. reverse proxy (Caddy/Traefik + own relay) vs. fully custom relay service.
- **Hardest part:** the auth/security model for exposing a local server to the internet — auth, TLS, rate limiting, abuse prevention.
- **Depends on:** licensing (§9.2) — if the relay is the closed paid component, its design is central to the whole business model.
- **Next touch:** architecture session, paired with the diagram (§9.5).

### 9.4 Camera Integration — ✅ Decided (strategy) / ⚪ Open (build details)
- ONVIF for discovery + RTSP for streaming, brand-agnostic baseline (§2.3).
- Frigate (MIT, MQTT-based) integrated as optional companion, not rebuilt from scratch.
- Community-maintained camera compatibility list rather than promising universal ONVIF support.
- **Open:** how Frigate's optional presence affects install complexity/UX for non-technical users (§4.5); whether camera support ships at launch or later (§9.9).
- **Status:** no code yet.

### 9.5 System Architecture Diagram — ⚪ Open
- Needs to tie together: local server, the Plugin/Ingest pipeline (Govee BLE + Tuya LAN, and any future plugins), ONVIF cameras, Frigate companion, and the optional remote-access relay.
- **Premise updated:** the original brief said "MQTT broker + ESP32 BLE proxies" — that's superseded by ADR 0013 (see §2.2). The diagram should show the JSON Registry/Inbox contract, with MQTT shown only as an optional future bridge plugin and as Frigate's own dependency.
- Best done alongside §9.3, once remote-access architecture has a candidate shape.

### 9.6 Data Model / Schema — ✔️ Core built / ⚪ Multi-user + lineage open
- **Built:** rooms, enclosures, animals, plants, sensors, plugs, care events, readings, schedules, and alerting — see §8 and `db/schema.sql`. Relationships and fields are designed and migrated (13 ADRs).
- **Still open (both flagged "cheap now, expensive later" — §4.3):**
  - **No user/household/owner model.** No `user` table, no owner/household column anywhere. Fine under "one instance = one household," but zero scaffolding for the roadmap's multi-user feature. Needs a conscious call, not silent drift.
  - **No animal-lineage fields.** `animal` has no `dam_id`/`sire_id` (or equivalent). Schema is still actively growing, so this is still the cheap moment.
- Tracked in more detail in the `reqs-alignment-review` punch list (memory).

### 9.7 Hardware Recommendations — ⚪ Open
- Not yet scoped. Likely covers: which hardware to recommend/support (Pi boards, sensor brands, plug/camera brands), reference kit vs. BYO, and how hardware choices interact with the Plugin pattern.
- **Constraint already known:** the Govee BLE Plugin needs host Bluetooth, which pushes the non-technical-user path toward the Pi-image target over Docker (§2.5).
- Coupled to packaging (§4.4).

### 9.8 Tech Stack — ✔️ Decided by use
- Python + FastAPI + Jinja2 + SQLite; `bleak` / `tinytuya` for device I/O; `jsonschema` for the Plugin Event contract. No ORM — hand-written SQL against `db/schema.sql`. Three-process architecture (ADR 0001).
- Not formally ratified in a standalone ADR beyond ADR 0001, but settled in practice. Revisit only if a hard constraint forces it (e.g. the Pi-class performance target, or a mobile/API rewrite).

### 9.9 Feature Phasing — 🟡 Recommended, not confirmed
- **Phase 1 (largely built):** environment monitoring — sensors, plugs, schedules, alerts, dashboard, admin (§8, `docs/PHASE1.md`).
- **Phase 2 (partly built):** animal & care records, plant health — care-event logging exists.
- **Later:** cameras, breeding tools, multi-user, remote access.
- **Open:** the exact order and cut line for v1 launch — especially whether cameras and any multi-user scaffolding are in v1 or deferred.

### 9.10 Naming / Branding — ✅ Decided (2026-09-23, executed 2026-09-27)
- See Project Plan §10. The app is **Husbandry Tracker**, a CaskAbove product — see `docs/adr/0020-rename-to-husbandry-tracker.md`.

### 9.11 Go-to-Market — 🟡 Recommended, not confirmed
- Organic-first: Reddit (r/reptiles + species subs), FB husbandry groups, Discord, GitHub/HN. Paid ads only as a modest ~$300–500 test if desired.
- **Not committed:** timing of marketing push relative to launch / licensing / website readiness.

### 9.12 Legal / Business Formation — ⚪ Open
- LLC not yet formed (cost-estimated: ~$150–700 lean bootstrap, up to $1,400–5,000 polished).
- ToS / privacy-policy templates not sourced.
- Interacts with licensing (§9.2) and the remote-access relay (§9.3) — a hosted paid service raises different liability/ToS needs than pure open-source distribution.

### 9.13 Website — ⚪ Open
- Not built. Cost-estimated only (~$10–40/mo recurring infra to start).

### 9.14 Plugin Architecture — Follow-ups — ⚪ Open *(from 2026-08-28 review)*
The ADR 0013 pipeline is built and working. Open decisions on top of it:
- **Finish the generic migration.** `web/admin_queries.py` still threads `mac_address` / `tuya_device_id` / `tuya_local_key` / `switch_dps_key` through every signature, with `_decode_sensor` / `_decode_plug` shims backfilling legacy keys. Storage is generic; the UI is still vendor-hardcoded. Decide: commit to generic end-to-end, or accept the shims as permanent. *(**2026-08-28 round-trip:** a separate session briefly reframed this as "subsumed by" Jira's `RHA-22` storage-abstraction ticket — see §9.15's note below. `RHA-22` was descoped the same day, so this item was never actually subsumed by anything; it stands exactly as originally written. Noted here only so a reader following that thread doesn't chase a dead end.)*
- **Plugin manifest.** No way for core to know a plugin exists before a device is registered to it; Admin device-registration forms are hand-coded per vendor. A `plugins/<name>/manifest.json` (display name, the fields its External ID / Plugin Config need, the `kind`s it emits, the `schema_version` it speaks) would let Admin render forms generically and make "drop in a plugin in any language" real.
- **Observation-only vs. control.** Every plugin today is a read-only observer; Target Schedule is intent that's never enforced. Decide whether core → device control is ever in scope; if so, the Registry channel is where it belongs and the contract should reserve room now. If not, say so in ADR 0013.
- **Secrets on disk.** `plugin_config` (e.g. Tuya `local_key`) is plaintext in SQLite and copied plaintext into `data/registry/*.json`. Acceptable for local-first single-user; revisit when §9.6 multi-user lands.
- **Schema-version policy.** `schema_version` is `const 1` today. Define the migration/compat story before v2 is needed (Ingest currently quarantines mismatches).
- **Author docs.** A short `docs/PLUGIN_AUTHORS.md` pointing at the JSON Schema + the Registry/Inbox contract would validate the "any language" claim.

### 9.15 Entity Schema Layer (Python) — 🟡 Models built, not wired in *(all 7 tracked entities landed 2026-08-28)*
There's no typed entity-schema layer. Entity shape lives in three places that can drift: `db/schema.sql` (CHECK constraints), scattered `_validate_*` functions in `web/admin_queries.py`, and template assumptions. Rows travel as bare `dict`s with shim keys.
- **Proposal:** one typed definition per entity (room, enclosure, animal, plant, sensor, plug, care event, …), reused across Admin validation, the `tools/register_device.py` CLI, a future REST API, and the open-format export (constraint #4).
- **Recommended shape:** Pydantic v2 (already pulled in by FastAPI — now also listed directly in `requirements.txt` since `schemas/` depends on it, not just transitively); `Base` / `Create` / `Update` / `Read` split per entity; a `schemas/enums.py` consolidating the string-literal enums currently scattered as tuples (`ENCLOSURE_TYPES`, `CARE_EVENT_KINDS`, `EVENT_KINDS`, tracking/controller/alert kinds).
- **Boundaries:** field/shape validation in the models; cross-row invariants (Room-XOR-Enclosure-set, Manual Sensor needs a Target Range, controller kind needs a setpoint) stay in a service layer but import the shared enums/field lists. Sensor Target Range derives from `schemas/enclosure_types.py`, not re-listed. A test asserts each model agrees with `PRAGMA table_info(<table>)` so `schema.sql` stays the single source of truth for storage.
- **Timing:** same "schema is still growing, do it now" argument as §9.6. Suggested first slice: `enums.py` + one entity as a pattern to react to, then migrate the rest.
- **Done (first slice):** `schemas/enums.py` (`TrackingMode`, `ControllerKind`, `AlertState`, `SensorAlertCondition`, `PlugAlertCondition`, `CareEventKind` — `str, Enum` not `StrEnum`, matching `web/status.py`'s existing pattern since local dev is still Python 3.10). `schemas/sensor.py` (`SensorBase`/`Create`/`Update`/`Read`) — target-range fields generated from `schemas/enclosure_types.py`'s `TARGET_RANGE_METRICS` rather than re-listed; model validators mirror `sensor`'s two single-table CHECK constraints (tracking_mode/plugin/external_id coupling, enclosure_id/room_id XOR) exactly. `schemas/test_entity_schema.py` asserts `SensorRead` against a real `PRAGMA table_info(sensor)` on an in-memory DB built from `db/schema.sql`; passing. `pytest` added to `requirements.txt` (dev/test only) since this is the first test in the repo.
- **Done (second slice, plug):** `schemas/plug.py` (`PlugBase`/`Create`/`Update`/`Read`) — same tracking_mode/plugin/external_id CHECK mirrored as a model validator; `purpose` mirrors its `CHECK (length(purpose) > 0)` via `Field(min_length=1)`; `controller_kind` typed as the `ControllerKind` enum so bad values reject automatically. Deliberately does NOT validate Room-XOR-Enclosure-set, Controller-Kind-needs-a-setpoint, or Target-Schedule-both-or-neither — none of those are actual `plug` CHECK constraints (confirmed against `db/schema.sql`: only one CHECK block exists, the tracking_mode one), and §9.15's own boundary list names all three as service-layer, staying in `web/admin_queries.py::_validate_plug`. `enclosure_ids` is carried on `PlugCreate`/`PlugUpdate` only (the write-time input for the separate `plug_enclosure` join table) — deliberately absent from `PlugRead` since it isn't a `plug` column, so `schemas/test_entity_schema.py`'s `PRAGMA table_info(plug)` check (now parametrized over both entities) stays honest. Verified: happy paths, all three CHECK-mirroring rejections, and confirmed the three deferred rules are *not* enforced at the model level.
- **Done (third slice, care_event, Jira RHA-25):** `schemas/care_event.py` (`CareEventBase`/`Create`/`Read` — no `Update`: there is no `update_care_event`/`delete_care_event` anywhere in the code, `log_care_event()` is insert-only, matching the append-only `sensor_reading` pattern; adding an unused Update class would itself be the speculative machinery this layer is trying to avoid). `kind` mirrors `care_event`'s one real CHECK via the `CareEventKind` enum type. The Spot-feed rule (`animal_id` only valid alongside `kind = 'feeding'`) is deliberately NOT modeled — `db/schema.sql`'s own comment on the table says explicitly it's "enforced in web/admin_queries.py rather than a CHECK", so it stays in `web/queries.py::log_care_event()`. Added to `schemas/test_entity_schema.py`'s parametrize list; all three entities pass.
- **Done (fourth slice, enclosure, Jira RHA-15):** `schemas/enclosure.py` (`EnclosureBase`/`Create`/`Update`/`Read`). `enclosure_type` deliberately does NOT get a new `EnclosureType` enum in `enums.py` — validated by a model validator checking membership against `schemas/enclosure_types.py`'s existing `ENCLOSURE_TYPES` tuple directly, per that module's own docstring and the RHA-15 correction. `EnclosureCreate` includes `room_id`/`fallback_sensor_id` (defaulted `None`) even though the real `create_enclosure()` doesn't accept them — a form-UX simplification (Room assignment is a deliberate follow-up edit), not a domain rule, so including them is harmless and keeps the model's shape uniform with Sensor/Plug. Two things NOT modeled on purpose: "Plant needs a Bioactive Enclosure" belongs to `plant`, not `enclosure` (will matter for `schemas/plant.py`); `fallback_sensor_id` has no cross-check anywhere in the app by design (see `update_enclosure()`'s own docstring), so there's genuinely nothing to mirror, not something deferred. Added to `schemas/test_entity_schema.py`; all four entities pass.
- **Done (fifth slice, room, Jira RHA-14):** `schemas/room.py` (`RoomBase`/`Create`/`Update`/`Read`). `room` has zero CHECK constraints in `db/schema.sql` (only `name`'s UNIQUE, DB-level, not modeled) — confirmed by reading the table directly — so `RoomBase` needs no model validator at all, the first entity where that's true. The Light Schedule both-or-neither rule is not a CHECK either (no CHECK block exists on this table); stays in `web/admin_queries.py::_validate_light_schedule()`, same shape as Plug's Target Schedule rule. `RoomCreate` includes the light fields (defaulted `None`) even though the real `create_room()` only accepts `name` — same UI-flow-simplification pattern as Enclosure's `room_id`/`fallback_sensor_id`. Added to `schemas/test_entity_schema.py`; all five entities pass.
- **Done (sixth slice, animal, Jira RHA-16):** `schemas/animal.py` (`AnimalBase`/`Create`/`Update`/`Read`). Simplest entity yet — zero CHECK constraints, zero UNIQUE constraints, no `_validate_animal` of any kind in `web/admin_queries.py`, so no model validator needed (second entity after Room where that's true). Unlike Room/Enclosure, `create_animal()`/`update_animal()` take the exact same field set — no UI-flow-simplification divergence to document; `AnimalCreate`/`AnimalUpdate` mirror the real functions one-for-one. Notable difference from every other entity so far: `animal` has **no `created_at` column** at all (confirmed against `db/schema.sql`'s actual `CREATE TABLE` block) — `AnimalRead` adds only `id`. Added to `schemas/test_entity_schema.py`; all six entities pass.
- **Done (seventh slice, plant, Jira RHA-17):** `schemas/plant.py` (`PlantBase`/`Create`/`Read` — no `Update`, same reasoning as `care_event`: no `update_plant()` exists anywhere, only `create_plant()`/`delete_plant()`). Zero CHECK constraints on `plant` — no model validator needed. The Bioactive gate ("only a Bioactive Enclosure can have Plants") is deliberately NOT modeled — confirmed by reading `create_plant()` directly, it queries `enclosure.bioactive` itself, a cross-row rule per §9.15's boundary, unchanged from what was flagged during the Enclosure slice. RHA-17's Jira description proposed fields (`planted_date`, `care_notes`) that don't exist in `db/schema.sql` — stale, corrected on the ticket (real columns: `enclosure_id`, `name`, `species`, `created_at`). Added to `schemas/test_entity_schema.py`; all seven entities pass.
- **All 7 originally-tracked entities are now built** (sensor, plug, care_event, enclosure, room, animal, plant). **Not done yet, deliberately:** none of them are wired into `web/admin_queries.py` / `web/queries.py` / `tools/register_device.py` — every slice was additive by design, not a replacement for the existing dict-based validation (see §9.14, still open, for that decision). `web/queries.py`'s own `CARE_EVENT_KINDS` list was left as-is rather than swapped for `schemas.enums.CareEventKind`. **Also not built:** `plant_health_log` (Plant Health observations — see CONTEXT.md: Plant Health) is a real table with no schema/ticket of its own; flagged, not built, to avoid scope-creeping past what's tracked.

---

## 10. Session Log

- **Session 3:** Pricing strategy finalized, cash-flow model built, camera strategy set, licensing recommendation made (unconfirmed), startup costs estimated, marketing approach recommended (uncommitted).
- **Session 4:** Project Plan / decision-tracker document created.
- **Session 5 (2026-08-25):** Technical Requirements doc v1 created, synthesizing decisions through Session 5 plus forward-looking build-strategy flags.
- **2026-08-25:** "Everything is a Plugin" pivot — ADR 0013. Sensor/plug identity generalized to `plugin`/`external_id`/`plugin_config`; Ingest process added; migration run.
- **2026-08-28:** Alignment review of the Project Plan against the built codebase. Project Plan merged into this document (§8–§10); statuses updated to reality; §9.14 and §9.15 opened.
- **2026-08-28:** §9.15 first slice — `schemas/enums.py`, `schemas/sensor.py`, `schemas/test_entity_schema.py`. See §9.15 for detail.
- **2026-08-28:** §9.15 second slice — `schemas/plug.py`, added to `schemas/test_entity_schema.py`. See §9.15 for detail.
- **2026-08-28:** A separate session ("Claude in IntelliJ") set up Jira (project `RHA`, "Reptile Husbandry App", `kevinramsey2002.atlassian.net`) mirroring this doc's §8/§9, and made a tech-stack pivot on `RHA-3`: storage backend pluggable (SQLite default, optional Postgres/TimescaleDB for advanced analytics), with a new `RHA-22` "design storage abstraction layer" ticket blocking the SQLite/Postgres implementation tickets. Handed off to this session via `handoff-storage-backend-pivot-2026-08-28.md`.
- **2026-08-28 (same day, later):** Verified the Jira pivot against the live Jira instance (ticket content matched the handoff doc), then grilled `RHA-22` (`grill-me`) — descoped it: no interface layer being built without a second real backend to design it against; SQLite stays unconditional, `db/schema.sql` stays the single source of truth, no change to `schemas/sensor.py`/`plug.py`. Updated `RHA-22` (Low priority, descope rationale), closed `RHA-23` (redundant — the app already *is* the SQLite implementation), noted on `RHA-24` that starting it is what re-opens `RHA-22`. Also corrected a stale `RHA-19` speculation (a `hub_id` reference that doesn't exist in `db/schema.sql`). Net effect on this doc: §9.14 and §9.15 are unaffected — the "subsumed by RHA-22" framing floated in the handoff never took effect.
- **2026-08-28 (same day, later still):** §9.15 third slice, `schemas/care_event.py` (Jira RHA-25). See §9.15 for detail.
- **2026-08-28 (same day, later still):** §9.15 fourth slice, `schemas/enclosure.py` (Jira RHA-15). See §9.15 for detail.
- **2026-08-28 (same day, later still):** §9.15 fifth slice, `schemas/room.py` (Jira RHA-14). See §9.15 for detail.
- **2026-08-28 (same day, later still):** §9.15 sixth slice, `schemas/animal.py` (Jira RHA-16). See §9.15 for detail.
- **2026-08-28 (same day, later still):** §9.15 seventh slice, `schemas/plant.py` (Jira RHA-17) — all 7 originally-tracked entities now built. Wiring into `web/admin_queries.py` (§9.14) and `plant_health_log` (untracked) remain open. See §9.15 for detail.

---

## 11. Change Log

- **v1 (2026-08-25):** Initial document, synthesizing decisions through Session 5 (pricing, packaging, camera strategy, licensing recommendation) plus forward-looking build-strategy flags for future roadmap items.
- **v2 (2026-08-28):** Absorbed `Reptile_App_Project_Plan.md` (now a stub). Added §8 Build Status and §10 Session Log. Rewrote §2.2 to reflect ADR 0013 (MQTT/ESP32 superseded by the Plugin/Ingest pipeline). Converted the Project Plan's 13-item tracker into §9, with statuses corrected against the actual codebase — data model (§9.6) and tech stack (§9.8) moved from "open" to "built"; feature phasing (§9.9) updated. Added §9.14 (plugin follow-ups) and §9.15 (Python entity-schema layer) from the 2026-08-28 review. Updated all cross-references that pointed at "Project Plan item N".
