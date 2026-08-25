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

// Spot-feed (see CONTEXT.md): one visible Animal picker per Feeding row, copied into the hidden
// animal_id field of whichever of the four small forms (Today/Yesterday/2 days ago/Advanced)
// actually gets submitted — avoids showing four duplicate pickers for one Feeding row.
function syncSpotFeedAnimal(select) {
    const row = select.closest(".care-row");
    row.querySelectorAll(".spot-feed-target").forEach(function (el) { el.value = select.value; });
}
