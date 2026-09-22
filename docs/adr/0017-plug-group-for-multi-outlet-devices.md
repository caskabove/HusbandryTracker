# Plug Group for multi-outlet Tuya devices

**Status:** accepted

Some Tuya power strips expose several independently-switched relays plus hardwired-always-on
outlets on one physical device — today each outlet is a separate `plug` row with no shared
identity, which reproduces the exact ambiguous-naming bug already hit once with Govee's six
"ambient" sensors. We're adding a real `plug_group` table (`id`, `name`, Room-XOR-Enclosure(s)
ownership — same pattern `plug` already uses) rather than a plain `group_name` text column on
`plug`, because a string-matched group is the same silent-typo-splits-the-group failure mode
again; a table gives rename-once semantics and a real id to hang the group's one shared behavior
on. That shared behavior — an All On/All Off action mirroring the strip's physical master
button — fans out ordinary per-Plug Commands to the group's Smart members (never the
Always-On Outlets, which have no relay to command); it is not a new Outbox/Plugin-level concept.

Group creation is **user-declared from a template** (a picker: "3 relays + USB + 3 always-on"),
not auto-detected from Tuya device metadata — this codebase doesn't currently read
category/product_id from `devices.json` at all, and guessing an undocumented field for one known
device model isn't worth the risk of silently mis-classifying others. Auto-detection can layer on
top of the same template mechanism later without a schema change.

See `CONTEXT.md`: Plug Group, Plug Group Template, Always-On Outlet, All On / All Off.
