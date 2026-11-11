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
// trackingSelectId/smartBlockId are both optional (pass null for either) — the Setup Wizard's own
// Plug step (see setup_plug.html) has no Tracking Mode choice at all (ADR 0031), only a Controller
// Kind picker, so it calls this with null for both rather than duplicating the rest of this logic.
function updatePlugFieldVisibility(trackingSelectId, controllerSelectId, smartBlockId, alwaysOnBlockId, scheduleBlockId, thermostatBlockId, hydrostatBlockId) {
    const trackingSelect = trackingSelectId ? document.getElementById(trackingSelectId) : null;
    const isSmart = trackingSelect ? trackingSelect.value === "smart" : false;
    const controllerKind = document.getElementById(controllerSelectId).value;
    setToggleBlock(document.getElementById(smartBlockId), isSmart);
    // Always On (see CONTEXT.md: Always On) and Target Schedule (see CONTEXT.md: Target Schedule,
    // Timer-Controlled) used to share one block under controller_kind = 'none' — RHA-95 split them
    // into their own Controller Kind values ('none' and 'timer' respectively), so each now gets
    // its own block instead.
    setToggleBlock(document.getElementById(alwaysOnBlockId), controllerKind === "none");
    setToggleBlock(document.getElementById(scheduleBlockId), controllerKind === "timer");
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
    const belongsToBlock = document.getElementById(belongsToBlockId);
    setToggleBlock(belongsToBlock, standalone);
    setToggleBlock(document.getElementById(tuyaCredsBlockId), standalone);
    // setToggleBlock just blanket-enabled every input under "Belongs to" (standalone case),
    // including the Room <select> that's normally kept `disabled` so it never submits while
    // Enclosure(s) mode is showing (and vice versa) — re-run that inner Room/Enclosure(s) toggle
    // now so only whichever side is actually visible stays enabled.
    const parentTypeSelect = belongsToBlock && belongsToBlock.querySelector('select[name="parent_type"]');
    if (parentTypeSelect) parentTypeSelect.dispatchEvent(new Event("change"));
}

// Add Plug / Add Plug Group: the "exactly one parent" rule (see CONTEXT.md: Plug, Plug Group) is
// fully checkable client-side, so catch it here instead of letting it round-trip through the
// server's redirect-and-redisplay error flow, which would otherwise clear every field the user
// already filled in. Picking a Plug Group (Add Plug only, hence the optional groupSelectId) supplies
// its own parent and skips this check entirely — see onAddPlugGroupChange.
function validatePlugParentOnSubmit(event, parentSelectId, enclosuresBlockId, errorId, groupSelectId) {
    const enclosuresBlock = document.getElementById(enclosuresBlockId);
    const errorEl = document.getElementById(errorId);
    enclosuresBlock.classList.remove("field-error");
    errorEl.style.display = "none";
    const groupSelect = groupSelectId ? document.getElementById(groupSelectId) : null;
    if (groupSelect && groupSelect.value) return true;
    if (document.getElementById(parentSelectId).value !== "enclosures") return true;
    const anyChecked = Array.from(enclosuresBlock.querySelectorAll('input[type="checkbox"]')).some((cb) => cb.checked);
    if (anyChecked) return true;
    event.preventDefault();
    enclosuresBlock.classList.add("field-error");
    errorEl.style.display = "";
    errorEl.scrollIntoView({ behavior: "smooth", block: "center" });
    return false;
}

// Clears the field-error highlight above as soon as the user starts fixing it (checking a box, or
// switching "Belongs to" away from Enclosure(s)), rather than leaving it lit until the next submit.
function clearPlugParentError(enclosuresBlockId, errorId) {
    document.getElementById(enclosuresBlockId).classList.remove("field-error");
    document.getElementById(errorId).style.display = "none";
}

// Admin's Users card "Reset Password" button (see admin_app.html; RHA-99) — a plain confirm-style
// prompt rather than a dedicated page, since this is a single hidden field on an otherwise-empty
// form. Blocks the submit (returns false) if the admin cancels or leaves it too short.
function promptResetPassword(event, form) {
    const newPassword = window.prompt("New password for this user (at least 8 characters):");
    if (!newPassword || newPassword.length < 8) return false;
    form.querySelector('[name="new_password"]').value = newPassword;
    return true;
}

// Two fields that must be both filled in or both left blank (e.g. a Timer/Light schedule's on-
// time and off-time — see CONTEXT.md: Target Schedule) — matched by `name` rather than `id` so one
// call works regardless of which form it's in. Skipped entirely while disabled (a hidden
// Controller-Kind-gated block, say), since a disabled field never submits either way.
function validateBothOrNeitherOnSubmit(event, name1, name2, errorId) {
    const form = event.target;
    const el1 = form.elements[name1];
    const el2 = form.elements[name2];
    const errorEl = errorId ? document.getElementById(errorId) : null;
    if (errorEl) errorEl.style.display = "none";
    if (!el1 || !el2 || el1.disabled || el2.disabled) return true;
    if (!!el1.value === !!el2.value) return true;
    event.preventDefault();
    if (errorEl) { errorEl.style.display = ""; errorEl.scrollIntoView({ behavior: "smooth", block: "center" }); }
    return false;
}

// Manual Sensor: needs at least one complete Target Range (min *and* max) on some metric — see
// CONTEXT.md: Target Range. Scans the submitting form for every enabled "..min.."/"..max.." pair
// (by swapping "min" for "max" in the field's own name) rather than hardcoding metric names, so it
// works unchanged across Enclosure Types, the Room-owned Sensor's fixed temp/humidity pair, and
// both the "foo_min"/"foo_max" and "min_foo"/"max_foo" naming conventions already in use.
// trackingSelectId is optional — omit it where the form has no Tracking Mode picker at all (every
// Sensor the Add-Pet/Setup wizards create is Manual by definition).
function validateSensorTargetRangeOnSubmit(event, trackingSelectId, errorId) {
    const trackingSelect = trackingSelectId ? document.getElementById(trackingSelectId) : null;
    const errorEl = document.getElementById(errorId);
    errorEl.style.display = "none";
    if (trackingSelect && trackingSelect.value !== "manual") return true;
    const form = event.target;
    const inputs = Array.from(form.querySelectorAll('input[type="number"]')).filter((el) => !el.disabled);
    const hasPair = inputs.some((el) => {
        if (!el.name.includes("min") || el.value === "") return false;
        const maxEl = inputs.find((o) => o.name === el.name.replace("min", "max"));
        return !!maxEl && maxEl.value !== "";
    });
    if (hasPair) return true;
    event.preventDefault();
    errorEl.style.display = "";
    errorEl.scrollIntoView({ behavior: "smooth", block: "center" });
    return false;
}

// At least one of several optional fields must be filled in (e.g. logging a Reading needs at
// least one metric value — see CONTEXT.md: Reading) — `selector` scopes the check to this one
// form/row rather than the whole page, since e.g. an Enclosure can list several Sensors' own
// "Log Reading" forms at once. Falls back to a plain alert() when there's no dedicated error
// element for this row (cheaper than threading a uniquely-id'd message into every repeated row).
function validateAtLeastOneOnSubmit(event, selector, errorId) {
    const form = event.target;
    const inputs = Array.from(form.querySelectorAll(selector)).filter((el) => !el.disabled);
    const errorEl = errorId ? document.getElementById(errorId) : null;
    if (inputs.some((el) => el.value !== "")) {
        if (errorEl) errorEl.style.display = "none";
        return true;
    }
    event.preventDefault();
    if (errorEl) {
        errorEl.style.display = "";
        errorEl.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
        alert("Enter at least one value.");
    }
    return false;
}

function onAlwaysOnChange(checkbox, onTimeId, offTimeId) {
    const disabled = checkbox.checked;
    [onTimeId, offTimeId].forEach(function (id) {
        const input = document.getElementById(id);
        input.disabled = disabled;
        if (disabled) input.value = "";
    });
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

// Dashboard drag-and-drop: drag an Enclosure panel onto a Room (or Ungrouped) to reassign it, or
// drag a Room section's own handle up/down to reorder Rooms (see CONTEXT.md: Room). Native HTML5
// Drag and Drop, no library. There's no single <form> spanning the drag source and drop target, so
// the actual change is a plain fetch() POST — matching every other action in this app, the result
// is a full page reload rather than a partial DOM update.
//
// Both drag sources share the same room-section ondragover/ondrop handlers below; onRoomDrop tells
// them apart by dataTransfer type — "text/plain" (an Enclosure's id) vs "application/x-room-id" (a
// Room's own id, set only by onRoomDragStart) — rather than by two separate drop handlers, since a
// single drop target still needs to pick exactly one interpretation of whatever was dropped on it.
function onEnclosureDragStart(event) {
    event.dataTransfer.setData("text/plain", event.currentTarget.dataset.enclosureId);
    event.dataTransfer.effectAllowed = "move";
    event.currentTarget.classList.add("dragging");
}

function onEnclosureDragEnd(event) {
    event.currentTarget.classList.remove("dragging");
}

// The handle is the drag source, not the whole .room-header (which also hosts the "edit this Room"
// link, Refresh button, and Log Reading forms) — but it's the Room's .room-section that needs the
// .dragging styling and that onRoomDrop below reorders, so this reaches up to it.
function onRoomDragStart(event) {
    const section = event.currentTarget.closest(".room-section");
    event.dataTransfer.setData("application/x-room-id", section.dataset.roomId);
    event.dataTransfer.effectAllowed = "move";
    section.classList.add("dragging");
}

function onRoomDragEnd(event) {
    event.currentTarget.closest(".room-section").classList.remove("dragging");
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
    const draggedRoomId = event.dataTransfer.getData("application/x-room-id");
    if (draggedRoomId) {
        await reorderRoom(draggedRoomId, event.currentTarget);
        return;
    }
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

// Moves draggedRoomId to just before targetSection's current position among every real Room
// section (Ungrouped has no data-room-id value and isn't a Room to order against, so a drop there
// is ignored — same for dropping a Room back onto itself). Sends the whole new top-to-bottom order
// rather than just a swap, since app.js has no persistent notion of "adjacent" beyond the live DOM.
async function reorderRoom(draggedRoomId, targetSection) {
    const targetRoomId = targetSection.dataset.roomId;
    if (!targetRoomId || targetRoomId === draggedRoomId) return;
    const order = Array.from(document.querySelectorAll(".room-section"))
        .map(function (section) { return section.dataset.roomId; })
        .filter(function (roomId) { return roomId; });
    const fromIndex = order.indexOf(draggedRoomId);
    if (fromIndex === -1) return;
    order.splice(fromIndex, 1);
    order.splice(order.indexOf(targetRoomId), 0, draggedRoomId);
    try {
        const response = await fetch("/rooms/reorder", {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded"},
            body: new URLSearchParams({room_ids: order.join(",")}),
        });
        if (response.ok) {
            location.reload();
        } else {
            alert("Couldn't reorder rooms — try again.");
        }
    } catch (err) {
        alert("Couldn't reorder rooms — try again.");
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
// this app. "Set your own" dismisses the prompt and expands exactly the unlogged non-Feeding
// kinds' own Advanced dropdowns (marked data-unlogged by the template) instead of forcing a
// choice — an unlogged Feeding is left alone rather than auto-opening the Log Feeding Dialog
// (see Log Feeding Dialog, ADR 0043), which would be a jarring modal-after-modal experience; the
// selector below naturally excludes it, since Feeding's own Advanced is a plain button, not a
// `.care-advanced` <details>, once this dialog exists.
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

// Quick Log popup (see CONTEXT.md: Quick Log) — one <dialog> per Animal on the Enclosure's Admin
// page (admin_enclosure.html), each holding that Animal's own Growth & Condition Log and Shed Log
// cards. Parameterized by dialogId rather than a fixed id, since an Enclosure can have several
// Animals and so several of these dialogs on one page.
function openQuickLogDialog(dialogId) {
    const dialog = document.getElementById(dialogId);
    if (!dialog) return;
    dialog.addEventListener("click", function (e) {
        if (e.target === dialog) dismissQuickLogDialog(dialogId);
    }, { once: true });
    if (!dialog.open) dialog.showModal();
}

function dismissQuickLogDialog(dialogId) {
    const dialog = document.getElementById(dialogId);
    if (dialog && dialog.open) dialog.close();
}

// Image Lightbox (see CONTEXT.md: Animal Photo, Enclosure Photo, Dashboard Thumbnail) — one shared
// #image-lightbox <dialog> per page, opened by clicking any photo thumbnail (an Animal card, an
// Enclosure's own photo, or a Dashboard panel's thumbnail) to show it at full size.
function openImageLightbox(src) {
    const dialog = document.getElementById("image-lightbox");
    if (!dialog) return;
    dialog.querySelector("img").src = src;
    dialog.addEventListener("click", function (e) {
        if (e.target === dialog) dismissImageLightbox();
    }, { once: true });
    if (!dialog.open) dialog.showModal();
}

function dismissImageLightbox() {
    const dialog = document.getElementById("image-lightbox");
    if (dialog && dialog.open) dialog.close();
}

function useOwnCareDates() {
    dismissCarePrompt();
    document.querySelectorAll('.care-row[data-unlogged="true"] .care-advanced').forEach(function (details) {
        details.open = true;
    });
}

openCarePromptIfNeeded();

// Log Feeding Dialog (see CONTEXT.md: Log Feeding Dialog; ADR 0043) — the one dialog that logs a
// Feeding Care Event and its Feeding Detail together, opened by Today/Yesterday/2-days-ago (Date
// locked to that offset) or Advanced (Date editable, no day pre-picked, for backdating/catching
// up). feedingDefaultsByWho is read once per open from the dialog's own data-defaults attribute
// (embedded by admin_enclosure.html from get_enclosure()'s per-Who lookup, web/admin_queries.py)
// rather than fetched live on every Who switch.
let feedingDefaultsByWho = {};

// Mirrors admin_create_care_event()'s own days_ago -> occurred_at computation (web/admin.py) —
// "now" minus N whole days, keeping the current time-of-day — purely for display in the locked
// label; the actual value logged is still computed server-side from days_ago at submit time.
function formatLockedFeedingDate(daysAgo) {
    const d = new Date();
    d.setDate(d.getDate() - parseInt(daysAgo, 10));
    return d.toLocaleString(undefined, {
        weekday: "short", month: "short", day: "numeric", year: "numeric",
        hour: "numeric", minute: "2-digit",
    });
}

function openLogFeedingDialog(daysAgo) {
    const dialog = document.getElementById("log-feeding-modal");
    if (!dialog) return;
    try {
        feedingDefaultsByWho = JSON.parse(dialog.dataset.defaults || "{}");
    } catch (e) {
        feedingDefaultsByWho = {};
    }
    const daysAgoField = document.getElementById("log-feeding-days-ago");
    const occurredAtField = document.getElementById("log-feeding-occurred-at");
    const lockedLabel = document.getElementById("log-feeding-date-locked");
    const editableField = document.getElementById("log-feeding-date-editable-label");
    if (daysAgo === "advanced") {
        daysAgoField.value = "";
        occurredAtField.value = "";
        lockedLabel.hidden = true;
        editableField.hidden = false;
    } else {
        daysAgoField.value = daysAgo;
        occurredAtField.value = "";
        editableField.hidden = true;
        lockedLabel.hidden = false;
        lockedLabel.textContent = "Logging for: " + formatLockedFeedingDate(daysAgo);
    }
    const whoField = document.getElementById("log-feeding-who");
    whoField.value = "";
    applyFeedingDefaultsForWho("");
    if (!dialog.open) dialog.showModal();
}

function dismissLogFeedingDialog() {
    const dialog = document.getElementById("log-feeding-modal");
    if (dialog && dialog.open) dialog.close();
}

function onLogFeedingWhoChange(select) {
    applyFeedingDefaultsForWho(select.value);
}

// Clear-then-refill (see CONTEXT.md: Log Feeding Dialog) — wipes the previous Who's values before
// loading the new Who's own last Feeding, rather than leaving a stale mix on screen; a Who with no
// prior Feeding here just clears, since there's nothing to default from.
function applyFeedingDefaultsForWho(who) {
    const defaults = feedingDefaultsByWho[who] || null;
    document.getElementById("log-feeding-food").value = (defaults && defaults.food) || "";
    document.getElementById("log-feeding-count").value = (defaults && defaults.count != null) ? defaults.count : "";
    document.getElementById("log-feeding-prey-state").value = (defaults && defaults.prey_state) || "";
    document.getElementById("log-feeding-result").value = (defaults && defaults.result) || "accepted";
}

(function initLogFeedingDialog() {
    const dialog = document.getElementById("log-feeding-modal");
    if (!dialog) return;
    dialog.addEventListener("click", function (e) {
        if (e.target === dialog) dismissLogFeedingDialog();
    });
})();

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

// Species Profile (see CONTEXT.md: Species Profile, Knowledge Base; ADR 0054) — an optional,
// never-persisted picker on the Add-Enclosure and Add-Sensor forms (Setup Wizard, Add New Pet
// Wizard, and ordinary Admin alike) that only pre-fills other fields with suggested starting
// values; the pick itself is never submitted anywhere. SPECIES_PROFILES/SPECIES_PROFILE_GROUPS used
// to be hardcoded literals right here — they're now server-rendered from the editable Knowledge
// Base tables (see web/species_kb_queries.py's species_profile_js_context, schemas/
// species_profile_kb.py) by web/templates/_species_profile_data.html, included on every page that
// needs them, before this file's own <script> tag. Every function below still reads the two
// globals exactly as it always did — only where the data comes from changed.

// Rebuilds a Species Profile <select>'s options for the given Enclosure Type, keeping its current
// selection if that profile is still offered under the new type. Called once on page load (Sensor
// forms, whose Enclosure Type is fixed) and again on every Enclosure Type change (Enclosure forms,
// where the user can still switch it).
// Add/Edit Animal's Knowledge Base species picker (web/templates/_animal_species_select.html;
// RHA-103): a specific species fills the same form's common/scientific name fields, which stay
// editable afterwards. Catch-alls and "none" carry no data-common, so they leave the names alone.
function onAnimalSpeciesPick(select) {
    const option = select.options[select.selectedIndex];
    if (!option || !option.dataset.common) return;
    _setNamedField(select.form, "common", option.dataset.common);
    _setNamedField(select.form, "scientific", option.dataset.scientific || "");
}

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

function _setFieldInContainer(container, name, value) {
    if (!container) return;
    const field = container.querySelector('[name="' + name + '"]');
    if (field) { field.value = value; revealField(field); }
}

// Plugs and Sensors' global Add Sensor form only (see admin_index.html; ADR 0050/0055) — merges
// the per-Enclosure and per-Room Add Sensor forms into one, so it needs this scoped sibling of
// onSensorSpeciesProfileChange above: admin_index.html renders all four Enclosure Types' Target
// Range/Volatility blocks at once (one shown+enabled, three hidden+disabled, picked by the chosen
// Enclosure's own data-enclosure-type), so looking a field up by name alone across the whole form
// (as _setNamedField does) would be ambiguous — "temperature" alone appears in every block. This
// writes into the one active block's own fields instead.
function onGlobalSensorEnclosureChange(enclosureSelect, speciesProfileSelectId, zoneWrapId, zoneSelectId) {
    const option = enclosureSelect.options[enclosureSelect.selectedIndex];
    const enclosureType = option ? option.dataset.enclosureType : null;
    ["basic", "freshwater", "saltwater", "amphibian"].forEach(function (type) {
        setToggleBlock(document.getElementById("add-sensor-global-metrics-" + type), type === enclosureType);
    });
    const profileSelect = document.getElementById(speciesProfileSelectId);
    populateSpeciesProfileSelect(profileSelect, enclosureType);
    onGlobalSensorSpeciesProfileChange(profileSelect, zoneWrapId, zoneSelectId, enclosureSelect.id);
}

// Scoped sibling of onSensorSpeciesProfileChange — see onGlobalSensorEnclosureChange above for why.
function onGlobalSensorSpeciesProfileChange(select, zoneWrapId, zoneSelectId, enclosureSelectId) {
    const enclosureSelect = document.getElementById(enclosureSelectId);
    const option = enclosureSelect ? enclosureSelect.options[enclosureSelect.selectedIndex] : null;
    const enclosureType = option ? option.dataset.enclosureType : null;
    const container = enclosureType ? document.getElementById("add-sensor-global-metrics-" + enclosureType) : null;
    const profile = SPECIES_PROFILES[select.value];
    const hasTemp = !!(profile && profile.basking);
    const zoneWrap = zoneWrapId ? document.getElementById(zoneWrapId) : null;
    if (zoneWrap) setToggleBlock(zoneWrap, hasTemp);
    if (!container) return;
    if (hasTemp) {
        const zone = zoneSelectId ? document.getElementById(zoneSelectId).value : "ambient";
        const range = _tempRangeForZone(profile, zone);
        _setFieldInContainer(container, "temp_min_f", range[0]);
        _setFieldInContainer(container, "temp_max_f", range[1]);
    }
    if (profile && profile.humidity) {
        _setFieldInContainer(container, "humidity_min", profile.humidity[0]);
        _setFieldInContainer(container, "humidity_max", profile.humidity[1]);
    }
}

// Scoped sibling of onSensorZoneChange — see onGlobalSensorEnclosureChange above for why.
function onGlobalSensorZoneChange(zoneSelect, speciesSelectId, enclosureSelectId) {
    const speciesSelect = document.getElementById(speciesSelectId);
    const profile = SPECIES_PROFILES[speciesSelect.value];
    const range = _tempRangeForZone(profile, zoneSelect.value);
    if (!range) return;
    const enclosureSelect = document.getElementById(enclosureSelectId);
    const option = enclosureSelect ? enclosureSelect.options[enclosureSelect.selectedIndex] : null;
    const enclosureType = option ? option.dataset.enclosureType : null;
    const container = enclosureType ? document.getElementById("add-sensor-global-metrics-" + enclosureType) : null;
    _setFieldInContainer(container, "temp_min_f", range[0]);
    _setFieldInContainer(container, "temp_max_f", range[1]);
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

// Every Setup Wizard step's own forward-navigation link/button ("Continue", "Skip — I just have
// one enclosure", "I'm done with this enclosure") sits right next to that step's own Add form —
// easy to click by mistake instead of submitting first, which silently discards whatever was
// typed (no partial-save, same as every other Setup Wizard form; see RHA-95). Warns instead of
// leaving silently whenever the named form has anything typed/checked into it. Chain multiple
// calls with && in one onclick (see setup_room_devices.html) to check more than one form on a
// step that has two (Room Sensor and Room Plug) — each check is independent, so if both have
// unsaved data the visitor sees one confirm per form, in order.
function onWizardContinueClick(event, formId, entityLabel, addButtonLabel) {
    const form = document.getElementById(formId);
    if (!form) return true;
    const hasUnsavedData = Array.prototype.some.call(form.elements, function (el) {
        // "hidden" excluded — e.g. setup_animals.html's carried-over species_profile/life_stage
        // fields are never empty once a Species Profile was picked earlier in the wizard, but
        // that's not user-typed input this click would lose. "select-one"/"select-multiple"
        // excluded too — e.g. setup_plug.html's own Controller Kind always defaults to a non-blank
        // value ("none"), which isn't "entered" the way a typed or checked field is; whatever a
        // select reveals when changed (a Target Temperature, an on/off time) is still its own
        // separate, checked element below.
        if (el.disabled || !el.name || el.type === "submit" || el.type === "button"
            || el.type === "hidden" || el.type === "select-one" || el.type === "select-multiple") return false;
        if (el.type === "checkbox" || el.type === "radio") return el.checked;
        return el.value != null && el.value.trim() !== "";
    });
    if (hasUnsavedData && !confirm(`You’ve entered ${entityLabel} details above but haven’t clicked "${addButtonLabel}" yet — they’ll be lost if you leave now. Continue without saving them?`)) {
        event.preventDefault();
        return false;
    }
    return true;
}

// Knowledge Base search (see CONTEXT.md: Knowledge Base; ADR 0054) — one search box filters every
// category table's rows live, by common name or scientific name, across all 7 tables at once. A
// category with zero matches collapses its whole section rather than leaving an empty heading and
// table behind.
function filterKnowledgeBase(query) {
    const needle = query.trim().toLowerCase();
    document.querySelectorAll(".kb-category").forEach(function (section) {
        let anyVisible = false;
        section.querySelectorAll("tbody tr[data-search]").forEach(function (row) {
            const match = !needle || row.dataset.search.indexOf(needle) !== -1;
            row.style.display = match ? "" : "none";
            if (match) anyVisible = true;
        });
        section.style.display = (anyVisible || !needle) ? "" : "none";
    });
}

// Genetics & Morph card on Edit Animal (see CONTEXT.md: Genetics; RHA-105). The Gene picked (or the
// Inheritance given for a new Gene) decides which Gene States are offered: Het/Possible Het only
// for Recessive, Super only for Co-dominant. The server enforces the same rule.
function onGeneticsGenePick(select) {
    const form = select.form;
    const isNew = select.value === "new";
    form.querySelectorAll(".genetics-new-gene").forEach(function (block) { setToggleBlock(block, isNew); });
    const option = select.options[select.selectedIndex];
    const inheritance = isNew ? form.elements.new_gene_inheritance.value : (option && option.dataset.inheritance);
    const validStates = JSON.parse(form.dataset.validStates || "{}")[inheritance];
    const stateSelect = form.elements.state;
    Array.from(stateSelect.options).forEach(function (o) {
        const allowed = !validStates || validStates.indexOf(o.value) !== -1;
        o.hidden = !allowed;
        o.disabled = !allowed;
    });
    if (stateSelect.selectedOptions[0] && stateSelect.selectedOptions[0].disabled) stateSelect.value = "visual";
    onGeneticsStateChange(stateSelect);
}

// Possible Het takes a percentage; Het takes Evidence (a Possible Het is never Proven). Works for
// the add form (fields inside the form) and each Genetics row (fields in the same table row).
function onGeneticsStateChange(select) {
    const scope = select.closest("tr") || select.form;
    scope.querySelectorAll(".genetics-percent").forEach(function (block) { setToggleBlock(block, select.value === "possible_het"); });
    scope.querySelectorAll(".genetics-evidence").forEach(function (block) { setToggleBlock(block, select.value === "het"); });
}
