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
// Everything starts expanded server-side (see dashboard.html) regardless of what's inside — this
// toggles by hand and remembers the result per viewer via localStorage (dashboard-collapsed:<key>,
// keyed off each container's own data-collapse-key), so the *last* state a viewer left a section in
// wins on their next visit, not some content-based heuristic. Per-browser, not shared — same
// tradeoff as any other localStorage use in this app; wrapped in try/catch since a private window or
// blocked site data can throw on either read or write.
const COLLAPSE_STORAGE_PREFIX = "dashboard-collapsed:";

function applySavedCollapseState() {
    try {
        document.querySelectorAll("[data-collapse-key]").forEach(function (container) {
            if (localStorage.getItem(COLLAPSE_STORAGE_PREFIX + container.dataset.collapseKey) === "1") {
                container.classList.add("collapsed");
            }
        });
    } catch (e) { /* localStorage unavailable — everything just stays expanded */ }
}

function toggleCollapse(button) {
    const container = button.closest(".room-section, .panel, .care-section");
    if (!container) return;
    container.classList.toggle("collapsed");
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
