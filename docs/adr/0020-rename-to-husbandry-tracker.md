# Rename HerpMonitor to Husbandry Tracker (a CaskAbove product)

**Status**: accepted

The app is becoming a published CaskAbove product and needed a name change: "HerpMonitor" →
"Husbandry Tracker", with CaskAbove as publisher. Since no installer had shipped yet (no version
tags, no release), this was a clean, one-time cutover with no existing install base to migrate —
the last point where identifiers could be changed for free.

**Decision**: the rename reaches every layer, not just display text — the technical slug
`HusbandryTracker` (PascalCase, no separator, matching the existing `HerpMonitor` →
`HerpMonitorSupervisor.exe` convention) replaces `HerpMonitor` in the exe names, the db filename
(`data/husbandrytracker.db`), the GitHub repo (`kevinramsey2002/HusbandryTracker`, renamed in place
— staying under the personal account rather than a CaskAbove org, since none exists yet), and the
local folder. The Inno Setup `AppId` GUID was reissued rather than kept, since Windows uses that
GUID (not the app name) to match installer runs to "the same product" — this is a distinct product
identity under CaskAbove, not a continuation of the abandoned HerpMonitor identity, and reissuing it
cost nothing with zero installs in the wild.

**CaskAbove is backstage, not in-app.** The running app (dashboard header, window/tray titles) says
only "Husbandry Tracker" — CaskAbove appears in the installer's publisher field, the LICENSE
copyright holder, and the README/GitHub org, the way a small software company brands a
single-product app without stamping the company name on every screen.

**License stays MIT**; only the copyright holder changed (`kevinramsey2002` → `CaskAbove`). The
rename is not a licensing decision, and going proprietary was explicitly considered and deferred as
out of scope here.

**Already-accepted ADRs (0001–0019) were left untouched.** They're historical records of decisions
made when the app was still called HerpMonitor; the name inside their prose is original wording,
not a stale reference to fix. Only forward-looking docs (`CONTEXT.md`, README, USER_GUIDE, HOWTOs)
and the codebase itself use the new name going forward.
