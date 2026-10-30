// Two-way field-group toggles for Admin forms — Tracking Mode (Smart/Manual) on Sensor/Plug forms,
// and Parent Type (Room/Enclosure(s)) on the Plug form (see CONTEXT.md: Tracking Mode, Plug).
//
// Each form has two blocks of fields; only one applies at a time. Hiding a block also disables its
// inputs so a stale value from the other side is never submitted (disabled fields are excluded
// from form submission), rather than relying on the server to ignore them.
function setToggleBlock(block, active) {
    if (!block) return;
    block.style.display = active ? "" : "none";
    block.querySelectorAll("input, select").forEach(function (el) { el.disabled = !active; });
}

// Generic: shows/enables firstBlockId when select's value equals firstValue, otherwise shows/
// enables secondBlockId.
function onToggleChange(select, firstValue, firstBlockId, secondBlockId) {
    const isFirst = select.value === firstValue;
    setToggleBlock(document.getElementById(firstBlockId), isFirst);
    setToggleBlock(document.getElementById(secondBlockId), !isFirst);
}

function onTrackingModeChange(select, smartBlockId, manualBlockId) {
    onToggleChange(select, "smart", smartBlockId, manualBlockId);
}

// View Data's Care Event cell (see CONTEXT.md: Period Slot; ADR 0026): the time input only applies
// — and is only submitted — when "Exact time" is picked; any Period Slot name overrides it
// server-side with that slot's own fixed hour, so hiding+disabling it here is just UX clarity, not
// load-bearing correctness.
function onPeriodSlotChange(select, timeInputId) {
    const input = document.getElementById(timeInputId);
    if (!input) return;
    const exact = select.value === "exact";
    input.style.display = exact ? "" : "none";
    input.disabled = !exact;
}

// Plug form only: Controller Kind (see CONTEXT.md) is an independent three-way select — none /
// thermostat / hydrostat — not a second value of Tracking Mode; a Plug can be Smart or Manual
// *and* Thermostat-/Hydrostat-Controlled at once (see ADR 0008). The Target Schedule block's
// visibility depends only on Controller Kind now (see ADR 0012 — it used to be Manual-only, back
// when it was Declared Schedule), so this recomputes all four blocks from current DOM state
// whenever either control changes. Wired to the onchange of both the tracking-mode select and the
// controller select, with the same six ids passed each time.
function updatePlugFieldVisibility(trackingSelectId, controllerSelectId, smartBlockId, scheduleBlockId, thermostatBlockId, hydrostatBlockId) {
    const isSmart = document.getElementById(trackingSelectId).value === "smart";
    const controllerKind = document.getElementById(controllerSelectId).value;
    setToggleBlock(document.getElementById(smartBlockId), isSmart);
    setToggleBlock(document.getElementById(scheduleBlockId), controllerKind === "none");
    setToggleBlock(document.getElementById(thermostatBlockId), controllerKind === "thermostat");
    setToggleBlock(document.getElementById(hydrostatBlockId), controllerKind === "hydrostat");
}

// Plug form only: Always On (see CONTEXT.md: Plug, Always On) is mutually exclusive with Target
// Schedule and lives inside the same scheduleBlockId div, so it already inherits that block's own
// show/hide-on-Controller-Kind-change behavior for free (setToggleBlock disables everything inside,
// including this checkbox, when the block is hidden). This just handles the second-level toggle
// within that block: checking Always On disables (and clears) the two time inputs so a stale value
// is never submitted alongside it.
// Add Plug form only: picking a Plug Group (see CONTEXT.md: Plug Group) hides/disables "Belongs
// to" and the Tuya device_id/local_key/ip fields, since add_plug_to_group() inherits both from the
// Group — only the new outlet's own DPS key (left outside tuyaCredsBlockId, see admin_index.html)
// still needs entering.
function onAddPlugGroupChange(select, belongsToBlockId, tuyaCredsBlockId) {
    const standalone = select.value === "";
    setToggleBlock(document.getElementById(belongsToBlockId), standalone);
    setToggleBlock(document.getElementById(tuyaCredsBlockId), standalone);
}

function onAlwaysOnChange(checkbox, onTimeId, offTimeId) {
    const disabled = checkbox.checked;
    [onTimeId, offTimeId].forEach(function (id) {
        const input = document.getElementById(id);
        input.disabled = disabled;
        if (disabled) input.value = "";
    });
}

// Spot-feed (see CONTEXT.md): one visible Animal picker per Feeding row, copied into the hidden
// animal_id field of whichever of the four small forms (Today/Yesterday/2 days ago/Advanced)
// actually gets submitted — avoids showing four duplicate pickers for one Feeding row.
function syncSpotFeedAnimal(select) {
    const row = select.closest(".care-row");
    row.querySelectorAll(".spot-feed-target").forEach(function (el) { el.value = select.value; });
}

// Dashboard: a Manual Sensor's Log Reading control (see dashboard.html's reading_log_form macro)
// starts collapsed to a single button naming the Sensor (e.g. "Log Probe Reading"); opening it
// pre-fills the datetime-local field with the current moment, so logging "now" needs no typing.
// Only fills it if still empty, so reopening after the user already picked a backdated time (e.g.
// closed by mis-click) doesn't clobber it.
function onReadingLogToggle(details) {
    if (!details.open) return;
    const input = details.querySelector('input[type="datetime-local"]');
    if (!input || input.value) return;
    const pad = (n) => String(n).padStart(2, "0");
    const now = new Date();
    input.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

// Dashboard: collapse/expand a Room section, Enclosure panel, or an Enclosure's own Care section.
// Room/Enclosure start expanded server-side, Care starts collapsed (see dashboard.html) — this
// toggles by hand and remembers the result per viewer via localStorage (dashboard-collapsed:<key>,
// keyed off each container's own data-collapse-key), so the *last* state a viewer left a section in
// wins on their next visit regardless of its server-rendered default. Per-browser, not shared — same
// tradeoff as any other localStorage use in this app; wrapped in try/catch since a private window or
// blocked site data can throw on either read or write. Exception: a Room section (the dashboard's
// top level) never remembers a manual collapse across loads (RHA-87) — it always starts expanded.
const COLLAPSE_STORAGE_PREFIX = "dashboard-collapsed:";

function applySavedCollapseState() {
    try {
        document.querySelectorAll("[data-collapse-key]").forEach(function (container) {
            if (container.classList.contains("room-section")) return;
            const saved = localStorage.getItem(COLLAPSE_STORAGE_PREFIX + container.dataset.collapseKey);
            if (saved === "1") {
                container.classList.add("collapsed");
            } else if (saved === "0") {
                container.classList.remove("collapsed");
            }
        });
    } catch (e) { /* localStorage unavailable — server-rendered default state stays as-is */ }
}

function toggleCollapse(button) {
    const container = button.closest(".room-section, .panel, .collapsible-section");
    if (!container) return;
    container.classList.toggle("collapsed");
    if (container.classList.contains("room-section")) return;
    const key = container.dataset.collapseKey;
    if (!key) return;
    try {
        localStorage.setItem(COLLAPSE_STORAGE_PREFIX + key, container.classList.contains("collapsed") ? "1" : "0");
    } catch (e) { /* localStorage unavailable — state just won't persist */ }
}

applySavedCollapseState();

// Dashboard drag-and-drop: drag an Enclosure panel onto a Room (or Ungrouped) to reassign it (see
// CONTEXT.md: Room). Native HTML5 Drag and Drop, no library. There's no single <form> spanning the
// drag source and drop target, so the actual reassignment is a plain fetch() POST — matching every
// other action in this app, the result is a full page reload rather than a partial DOM update.
function onEnclosureDragStart(event) {
    event.dataTransfer.setData("text/plain", event.currentTarget.dataset.enclosureId);
    event.dataTransfer.effectAllowed = "move";
    event.currentTarget.classList.add("dragging");
}

function onEnclosureDragEnd(event) {
    event.currentTarget.classList.remove("dragging");
}

function onRoomDragOver(event) {
    event.preventDefault();  // a dragover handler must call this, or drop never fires
    event.currentTarget.classList.add("drop-target");
}

function onRoomDragLeave(event) {
    event.currentTarget.classList.remove("drop-target");
}

async function onRoomDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.remove("drop-target");
    const enclosureId = event.dataTransfer.getData("text/plain");
    if (!enclosureId) return;
    const roomId = event.currentTarget.dataset.roomId;  // "" means Ungrouped (room_id -> NULL)
    try {
        const response = await fetch(`/enclosures/${enclosureId}/assign-room`, {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded"},
            body: new URLSearchParams({room_id: roomId}),
        });
        if (response.ok) {
            location.reload();
        } else {
            alert("Couldn't move that enclosure — try again.");
        }
    } catch (err) {
        alert("Couldn't move that enclosure — try again.");
    }
}

// Add Sensor forms' "Discover Devices" button (see ADR 0029, CONTEXT.md: Device Registration) —
// scans for ~20s and lists whatever Govee-looking devices answered, each as its own button that
// fills in *this same form's* MAC address field. Deliberately does NOT reload the page afterward,
// unlike every other action in this app (see onRoomDrop above) — the surrounding form may already
// be partway filled in (Label, Target Range, Volatility), and a reload would discard all of that
// for a result that's only ever used once, to fill in one field.
async function onDiscoverGoveeClick(button) {
    const macField = button.closest("form").querySelector('[name="mac_address"]');
    const results = button.parentElement.querySelector(".discover-results");
    results.style.display = "";
    results.innerHTML = '<p class="empty">Scanning for Govee sensors (about 20s)…</p>';
    button.disabled = true;
    try {
        const response = await fetch("/admin/sensors/discover", {method: "POST"});
        const data = await response.json();
        if (!response.ok || data.error) {
            results.innerHTML = `<p class="empty">${data.error || "Discovery failed — try again."}</p>`;
            return;
        }
        if (!data.devices.length) {
            results.innerHTML = '<p class="empty">No Govee sensors found — check Bluetooth is on, '
                + 'and the sensor is powered and in range.</p>';
            return;
        }
        results.innerHTML = "";
        data.devices.forEach(function (device) {
            const tempF = (device.temperature_c * 9 / 5 + 32).toFixed(1);
            const pick = document.createElement("button");
            pick.type = "button";
            pick.textContent = `${device.mac} — ${tempF}°F / ${device.humidity_pct.toFixed(0)}% RH`;
            pick.onclick = function () {
                macField.value = device.mac;
                results.style.display = "none";
            };
            results.appendChild(pick);
        });
    } catch (err) {
        results.innerHTML = '<p class="empty">Discovery failed — try again.</p>';
    } finally {
        button.disabled = false;
    }
}

// Care Setup Prompt (see CONTEXT.md: Care Setup Prompt, Care Interval; ADR 0040) — a dialog
// server-rendered only when at least one Care kind has no data yet (admin_enclosure.html), so this
// just opens it as a real modal on load; nothing to do when the dialog isn't on the page (every
// kind already resolved). "Start from Today" is a plain form submit, same as every other action in
// this app. "Set your own" dismisses the prompt and expands exactly the unlogged kinds' own
// Advanced dropdowns (marked data-unlogged by the template) instead of forcing a choice, showing
// one shared instruction once rather than forcing the user to discover the existing Log forms.
function openCarePromptIfNeeded() {
    const dialog = document.getElementById("care-prompt-modal");
    if (!dialog) return;
    // A click directly on the <dialog> element itself (not anything inside it) landed on the
    // ::backdrop — dismiss like clicking the X (same convention as graphs.js's graph modal).
    dialog.addEventListener("click", function (e) {
        if (e.target === dialog) dismissCarePrompt();
    });
    if (!dialog.open) dialog.showModal();
}

function dismissCarePrompt() {
    const dialog = document.getElementById("care-prompt-modal");
    if (dialog && dialog.open) dialog.close();
}

function useOwnCareDates() {
    dismissCarePrompt();
    document.querySelectorAll('.care-row[data-unlogged="true"] .care-advanced').forEach(function (details) {
        details.open = true;
    });
    const hint = document.getElementById("care-advanced-hint");
    if (hint) hint.hidden = false;
}

function dismissCareAdvancedHint() {
    const hint = document.getElementById("care-advanced-hint");
    if (hint) hint.hidden = true;
}

openCarePromptIfNeeded();

async function onDiscoverTuyaClick(button) {
    const form = button.closest("form");
    const deviceIdField = form.querySelector('[name="tuya_device_id"]');
    const localKeyField = form.querySelector('[name="tuya_local_key"]');
    const switchKeyField = form.querySelector('[name="switch_dps_key"]');
    const results = button.parentElement.querySelector(".discover-results");
    results.style.display = "";
    results.innerHTML = '<p class="empty">Asking Tuya’s cloud for your linked devices…</p>';
    button.disabled = true;
    try {
        const response = await fetch("/admin/plugs/discover-tuya", {method: "POST"});
        const data = await response.json();
        if (!response.ok || data.error) {
            results.innerHTML = `<p class="empty">${data.error || "Discovery failed — try again."}</p>`;
            return;
        }
        if (!data.devices.length) {
            results.innerHTML = '<p class="empty">No devices found on that Tuya account.</p>';
            return;
        }
        results.innerHTML = "";
        data.devices.forEach(function (device) {
            const pick = document.createElement("button");
            pick.type = "button";
            pick.textContent = `${device.name} (${device.category || "device"})`;
            pick.onclick = function () {
                deviceIdField.value = device.id;
                localKeyField.value = device.local_key;
                if (switchKeyField && device.switch_key_guess) {
                    switchKeyField.value = device.switch_key_guess;
                }
                results.style.display = "none";
            };
            results.appendChild(pick);
        });
    } catch (err) {
        results.innerHTML = '<p class="empty">Discovery failed — try again.</p>';
    } finally {
        button.disabled = false;
    }
}

// Species Profile (see CONTEXT.md: Species Profile) — an optional, never-persisted picker on the
// Add-Enclosure and Add-Sensor forms (Setup Wizard and ordinary Admin alike) that only pre-fills
// other fields with suggested starting values; the pick itself is never submitted anywhere. Ranges
// sourced from docs/reference/Reptile Care Parameters Knowledge Base.md. `basking`/`cool`/`night`
// are [min, max] °F; `humidity` is [min, max] %; `scientific` is the species' Latin name — present
// only on a real, specific species (never the "(other/unlisted)" catch-alls, Tortoise, Insect, or
// an aquatic value), so it doubles as the signal that this entry is specific enough to also carry
// forward onto the Setup Wizard's Animal step (see prefillAnimalSpecies below). `feeding` is
// {baby, adult} feeding_interval_days —
// a KB range like "every 5-7 days" is stored here already collapsed to its rounded midpoint (an
// omnivore/herbivore lizard with two parallel feeding tracks, e.g. a bearded dragon's daily salad
// alongside twice-weekly insects, is stored as whichever track recurs more often). A profile with no
// numeric fields at all (the "(other/unlisted)" catch-alls, Tortoise, Insect, and every aquatic
// value today) exists only so the dropdown represents everything its Enclosure Type can hold —
// picking one pre-fills nothing, same as picking no profile. "Lizard (other/unlisted)" in particular
// is deliberately never given an averaged number: the ten listed lizards alone span a 78-135°F
// basking range, so a single blanket "Lizard" figure would be badly wrong for most individual
// species, not just imprecise.
const SPECIES_PROFILES = {
    ball_python: { label: "Ball Python", scientific: "Python regius", basking: [88, 95], cool: [75, 80], night: [72, 78], humidity: [50, 70], feeding: { baby: 6, adult: 21 } },
    corn_snake: { label: "Corn Snake", scientific: "Pantherophis guttatus", basking: [85, 90], cool: [72, 78], night: [65, 70], humidity: [40, 60], feeding: { baby: 6, adult: 16 } },
    california_kingsnake: { label: "California Kingsnake", scientific: "Lampropeltis californiae", basking: [85, 90], cool: [70, 80], night: [65, 70], humidity: [40, 60], feeding: { baby: 6, adult: 11 } },
    western_hognose: { label: "Western Hognose Snake", scientific: "Heterodon nasicus", basking: [90, 95], cool: [70, 75], night: [60, 75], humidity: [30, 50], feeding: { baby: 6, adult: 12 } },
    boa_constrictor: { label: "Boa Constrictor", scientific: "Boa constrictor, Boa imperator", basking: [88, 95], cool: [75, 80], night: [72, 78], humidity: [60, 70], feeding: { baby: 9, adult: 21 } },
    honduran_milk_snake: { label: "Honduran Milk Snake", scientific: "Lampropeltis hondurensis", basking: [85, 88], cool: [72, 78], night: [65, 75], humidity: [40, 60], feeding: { baby: 6, adult: 11 } },
    rosy_boa: { label: "Rosy Boa", scientific: "Lichanura trivirgata", basking: [90, 95], cool: [75, 85], night: [65, 70], humidity: [30, 50], feeding: { baby: 9, adult: 16 } },
    kenyan_sand_boa: { label: "Kenyan Sand Boa", scientific: "Eryx colubrinus", basking: [90, 95], cool: [75, 80], night: [70, 75], humidity: [30, 50], feeding: { baby: 6, adult: 21 } },
    gopher_snake: { label: "Gopher Snake / Bullsnake", scientific: "Pituophis catenifer", basking: [85, 90], cool: [75, 80], night: [65, 70], humidity: [30, 50], feeding: { baby: 6, adult: 11 } },
    carpet_python: { label: "Carpet Python", scientific: "Morelia spilota", basking: [88, 95], cool: [75, 80], night: [70, 75], humidity: [50, 60], feeding: { baby: 9, adult: 18 } },
    snake_other: { label: "Snake (other/unlisted)", basking: [85, 95], cool: [70, 80], night: [65, 75], humidity: [30, 70], feeding: { baby: 7, adult: 14 } },
    bearded_dragon: { label: "Bearded Dragon", scientific: "Pogona vitticeps", basking: [105, 115], cool: [70, 85], night: [60, 72], humidity: [30, 40], feeding: { baby: 1, adult: 1 } },
    leopard_gecko: { label: "Leopard Gecko", scientific: "Eublepharis macularius", basking: [90, 95], cool: [70, 80], night: [60, 75], humidity: [30, 40], feeding: { baby: 1, adult: 3 } },
    crested_gecko: { label: "Crested Gecko", scientific: "Correlophus ciliatus", basking: [78, 82], cool: [70, 75], night: [65, 72], humidity: [60, 80], feeding: { baby: 1, adult: 2 } },
    blue_tongue_skink: { label: "Blue-Tongued Skink", scientific: "Tiliqua scincoides intermedia", basking: [105, 115], cool: [70, 80], night: [65, 75], humidity: [40, 60], feeding: { baby: 1, adult: 2 } },
    african_fat_tailed_gecko: { label: "African Fat-Tailed Gecko", scientific: "Hemitheconyx caudicinctus", basking: [88, 92], cool: [70, 80], night: [70, 75], humidity: [50, 70], feeding: { baby: 1, adult: 2 } },
    veiled_chameleon: { label: "Veiled Chameleon", scientific: "Chamaeleo calyptratus", basking: [85, 90], cool: [72, 78], night: [55, 65], humidity: [30, 50], feeding: { baby: 1, adult: 2 } },
    gargoyle_gecko: { label: "Gargoyle Gecko", scientific: "Rhacodactylus auriculatus", basking: [82, 85], cool: [70, 75], night: [65, 72], humidity: [50, 70], feeding: { baby: 1, adult: 2 } },
    tegu: { label: "Argentine Black and White Tegu", scientific: "Salvator merianae", basking: [120, 135], cool: [75, 85], night: [70, 75], humidity: [60, 80], feeding: { baby: 1, adult: 3 } },
    green_iguana: { label: "Green Iguana", scientific: "Iguana iguana", basking: [115, 125], cool: [75, 85], night: [73, 80], humidity: [60, 80], feeding: { baby: 1, adult: 1 } },
    uromastyx: { label: "Uromastyx", scientific: "Uromastyx spp.", basking: [120, 130], cool: [80, 85], night: [70, 80], humidity: [10, 35], feeding: { baby: 1, adult: 1 } },
    lizard_other: { label: "Lizard (other/unlisted)" },
    tortoise: { label: "Tortoise" },
    insect: { label: "Insect" },
    freshwater: { label: "Freshwater" },
    freshwater_planted: { label: "Freshwater (planted)" },
    saltwater_fish_only: { label: "Saltwater — Fish-Only" },
    saltwater_mixed: { label: "Saltwater — Mixed" },
    saltwater_reef: { label: "Saltwater — Reef" },
};

// Which profile keys are offered for each Enclosure Type, grouped for display — see CONTEXT.md:
// Species Profile. Amphibian has none yet (no reference data), same reason the aquatic groups below
// carry no numbers: the picker still exists everywhere so the dropdown's shape never changes as
// data gets added later, it's just empty for Amphibian today.
const SPECIES_PROFILE_GROUPS = {
    basic: [
        { label: "Snakes", keys: ["ball_python", "corn_snake", "california_kingsnake", "western_hognose", "boa_constrictor", "honduran_milk_snake", "rosy_boa", "kenyan_sand_boa", "gopher_snake", "carpet_python", "snake_other"] },
        { label: "Lizards", keys: ["bearded_dragon", "leopard_gecko", "crested_gecko", "blue_tongue_skink", "african_fat_tailed_gecko", "veiled_chameleon", "gargoyle_gecko", "tegu", "green_iguana", "uromastyx", "lizard_other"] },
        { label: "Other", keys: ["tortoise", "insect"] },
    ],
    freshwater: [
        { label: "", keys: ["freshwater", "freshwater_planted"] },
    ],
    saltwater: [
        { label: "", keys: ["saltwater_fish_only", "saltwater_mixed", "saltwater_reef"] },
    ],
    amphibian: [],
};

// Rebuilds a Species Profile <select>'s options for the given Enclosure Type, keeping its current
// selection if that profile is still offered under the new type. Called once on page load (Sensor
// forms, whose Enclosure Type is fixed) and again on every Enclosure Type change (Enclosure forms,
// where the user can still switch it).
function populateSpeciesProfileSelect(select, enclosureType) {
    if (!select) return;
    const groups = SPECIES_PROFILE_GROUPS[enclosureType] || [];
    const previous = select.value;
    select.innerHTML = "";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "— none / I'll enter my own —";
    select.appendChild(none);
    let stillOffered = false;
    groups.forEach(function (group) {
        const container = group.label ? document.createElement("optgroup") : select;
        if (group.label) container.label = group.label;
        group.keys.forEach(function (key) {
            const opt = document.createElement("option");
            opt.value = key;
            opt.textContent = SPECIES_PROFILES[key].label;
            container.appendChild(opt);
            if (key === previous) stillOffered = true;
        });
        if (group.label) select.appendChild(container);
    });
    select.value = stillOffered ? previous : "";
}

// Opens every ancestor <details> of a field that was just filled, so a pre-filled value under e.g.
// Setup Sensor's collapsed "+ more metrics" is visible instead of hidden.
function revealField(input) {
    if (!input) return;
    let details = input.closest ? input.closest("details") : null;
    while (details) {
        details.open = true;
        details = details.parentElement ? details.parentElement.closest("details") : null;
    }
}

function _setNamedField(form, name, value) {
    if (!form || value == null) return;
    const field = form.elements.namedItem(name);
    if (field) {
        field.value = value;
        revealField(field);
    }
}

// Enclosure Type changed on an Add-Enclosure form: rebuild the Species Profile options to match
// (e.g. switching from Basic to Saltwater swaps the snake/lizard list for Fish-Only/Mixed/Reef), and
// re-run the Species Profile change handler so Life Stage hides again if the new type's reset
// selection ("— none —") has no feeding data — same as picking "— none —" by hand would.
function onEnclosureTypeChangeForProfile(typeSelect, profileSelectId, lifeStageWrapId, lifeStageSelectId, feedingFieldName) {
    const profileSelect = document.getElementById(profileSelectId);
    populateSpeciesProfileSelect(profileSelect, typeSelect.value);
    onEnclosureSpeciesProfileChange(profileSelect, lifeStageWrapId, lifeStageSelectId, feedingFieldName);
}

// Species Profile changed on an Add-Enclosure form — see CONTEXT.md: Species Profile. Shows the
// Life Stage control only when the picked profile actually has feeding data (the "(other/unlisted)"/
// Tortoise/Insect/aquatic placeholders don't), and pre-fills feeding_interval_days from it.
function onEnclosureSpeciesProfileChange(select, lifeStageWrapId, lifeStageSelectId, feedingFieldName) {
    const profile = SPECIES_PROFILES[select.value];
    const hasFeeding = !!(profile && profile.feeding);
    const lifeStageWrap = lifeStageWrapId ? document.getElementById(lifeStageWrapId) : null;
    if (lifeStageWrap) setToggleBlock(lifeStageWrap, hasFeeding);
    if (hasFeeding && lifeStageSelectId && feedingFieldName) {
        const lifeStage = document.getElementById(lifeStageSelectId).value;
        _setNamedField(select.form, feedingFieldName, profile.feeding[lifeStage]);
    }
}

// Life Stage changed on an Add-Enclosure form — recomputes feeding_interval_days from whichever
// Species Profile is currently picked.
function onEnclosureLifeStageChange(lifeStageSelect, speciesSelectId, feedingFieldName) {
    const speciesSelect = document.getElementById(speciesSelectId);
    const profile = SPECIES_PROFILES[speciesSelect.value];
    if (profile && profile.feeding) {
        _setNamedField(speciesSelect.form, feedingFieldName, profile.feeding[lifeStageSelect.value]);
    }
}

// Collapses a Species Profile's three KB temperature figures (basking, cool side, night low) into
// the single min/max pair a Sensor's Target Range actually stores — see CONTEXT.md: Species
// Profile. Warm side reads the basking range as-is; Cool side and a single ambient Sensor both read
// the cool-side range with the night low as their floor, since neither placement should be expected
// to ever read a basking-level temperature.
function _tempRangeForZone(profile, zone) {
    if (!profile || !profile.basking) return null;
    if (zone === "warm") return profile.basking;
    return [profile.night[0], profile.cool[1]];
}

// Species Profile changed on an Add-Sensor form — see CONTEXT.md: Species Profile. Shows the zone
// question only when the picked profile has temperature data, pre-fills Target Temperature from the
// current zone, and pre-fills Target Humidity (zone-independent) unconditionally.
function onSensorSpeciesProfileChange(select, zoneWrapId, zoneSelectId, tempMinName, tempMaxName, humidityMinName, humidityMaxName) {
    const profile = SPECIES_PROFILES[select.value];
    const hasTemp = !!(profile && profile.basking);
    const zoneWrap = zoneWrapId ? document.getElementById(zoneWrapId) : null;
    if (zoneWrap) setToggleBlock(zoneWrap, hasTemp);
    if (hasTemp) {
        const zone = zoneSelectId ? document.getElementById(zoneSelectId).value : "ambient";
        const range = _tempRangeForZone(profile, zone);
        _setNamedField(select.form, tempMinName, range[0]);
        _setNamedField(select.form, tempMaxName, range[1]);
    }
    if (profile && profile.humidity) {
        _setNamedField(select.form, humidityMinName, profile.humidity[0]);
        _setNamedField(select.form, humidityMaxName, profile.humidity[1]);
    }
}

// Zone changed on an Add-Sensor form — recomputes Target Temperature from whichever Species Profile
// is currently picked.
function onSensorZoneChange(zoneSelect, speciesSelectId, tempMinName, tempMaxName) {
    const speciesSelect = document.getElementById(speciesSelectId);
    const profile = SPECIES_PROFILES[speciesSelect.value];
    const range = _tempRangeForZone(profile, zoneSelect.value);
    if (range) {
        _setNamedField(speciesSelect.form, tempMinName, range[0]);
        _setNamedField(speciesSelect.form, tempMaxName, range[1]);
    }
}

// Setup Wizard only: the Species Profile picked on the Enclosure step carries forward through the
// wizard's own query-string chain (never persisted — same "never stored" rule as the picker itself,
// see CONTEXT.md: Species Profile; Setup Wizard) to pre-fill the Animal step's Common/Scientific
// fields. Only fires for a profile with a `scientific` name — the catch-alls/placeholders are never
// specific enough to be worth stamping onto an Animal row.
function prefillAnimalSpecies(speciesKey) {
    const profile = SPECIES_PROFILES[speciesKey];
    if (!profile || !profile.scientific) return;
    const commonField = document.querySelector('input[name="common"]');
    const scientificField = document.querySelector('input[name="scientific"]');
    if (commonField) commonField.value = profile.label;
    if (scientificField) scientificField.value = profile.scientific;
}

// Setup Wizard's Plug step only: "I'm done with this enclosure" is a plain navigation link sitting
// right next to "Add Plug" — easy to click by mistake instead of submitting first, which silently
// discards whatever was typed (no partial-save, same as every other Setup Wizard form). Warns
// instead of leaving silently whenever the Plug form has anything typed/checked into it.
function onSetupDoneClick(event, formId) {
    const form = document.getElementById(formId);
    if (!form) return true;
    const hasUnsavedData = Array.prototype.some.call(form.elements, function (el) {
        if (el.disabled || !el.name || el.type === "submit" || el.type === "button") return false;
        if (el.type === "checkbox" || el.type === "radio") return el.checked;
        return el.value != null && el.value.trim() !== "";
    });
    if (hasUnsavedData && !confirm('You’ve entered Plug details above but haven’t clicked "Add Plug" yet — they’ll be lost if you leave now. Continue without saving them?')) {
        event.preventDefault();
        return false;
    }
    return true;
}
