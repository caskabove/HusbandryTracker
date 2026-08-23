// Tracking Mode toggle for Sensor/Plug Admin forms (see CONTEXT.md: Tracking Mode).
//
// Each form has a "Smart"/"Manual" block of fields; only one applies at a time. Hiding a block
// also disables its inputs so a stale value from the other mode is never submitted (disabled
// fields are excluded from form submission), rather than relying on the server to ignore them.
function setTrackingModeBlock(block, active) {
    if (!block) return;
    block.style.display = active ? "" : "none";
    block.querySelectorAll("input, select").forEach(function (el) { el.disabled = !active; });
}

function onTrackingModeChange(select, smartBlockId, manualBlockId) {
    const isSmart = select.value === "smart";
    setTrackingModeBlock(document.getElementById(smartBlockId), isSmart);
    setTrackingModeBlock(document.getElementById(manualBlockId), !isSmart);
}
