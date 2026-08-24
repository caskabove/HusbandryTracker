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
