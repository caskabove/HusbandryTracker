# Introduce App Admin as a distinct top-level page, home for cross-cutting app config starting with Plugins

**Status**: accepted

**Context**: ADR 0045 built an Admin "Plugins" card without specifying which Admin — it landed on
the existing `/admin` page, labeled "Plugs and Sensors" in nav, alongside a Settings card and a
Tuya Cloud Credentials card that are also app-wide config with nothing really to do with Plugs or
Sensors specifically. Meanwhile CONTEXT.md already uses "Admin page" to mean something else
entirely: a specific Room's or Enclosure's own per-entity settings screen, reached by drilling into
that one Room/Enclosure. Nothing in the app's nav is actually labeled "Admin" today.

**Decision**: add a new top-level page, `/admin/app`, labeled "Admin" in nav — distinct from both
"Plugs and Sensors" and the per-entity Admin-page sense already in CONTEXT.md (see CONTEXT.md: App
Admin). Move the existing Plugins card there from "Plugs and Sensors," which keeps only its
Sensors/Plug Groups/Plugs sections, now actually matching its own name. App Admin is meant as the
ongoing home for this kind of cross-cutting, non-entity-specific config — Settings and Tuya Cloud
Credentials are expected to move here too, as later, separate work, not bundled into this change.

**Considered Options**:
- **Rename "Plugs and Sensors" to "Admin" in place** — rejected: Settings, Tuya Cloud Credentials,
  and Plugins aren't about Plugs or Sensors either, and keeping the actual Sensors/Plug Groups/Plugs
  management under an "Admin" label would make that page's real device-management role less
  discoverable, not more.
- **Scope the new page to Plugin management only** — rejected: Settings and Tuya Cloud Credentials
  are the same kind of app-wide, non-entity-specific config Plugins is; a Plugins-only page would
  just mean another new page needed shortly after for the next thing like it.

**Consequences**: the Plugins card's activate/deactivate routes (`web/admin.py`) redirect to
`/admin/app/` instead of `/admin/`. "Plugs and Sensors" (`admin_index.html`) loses its Plugins
section. Settings and Tuya Cloud Credentials stay on "Plugs and Sensors" for now — moving them is
separate future work, not part of this change.
