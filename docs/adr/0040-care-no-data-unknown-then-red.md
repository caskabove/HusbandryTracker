# No-data Care kinds show Unknown, not Red, until ignored 3 times

**Context**: `care_interval_status()` previously returned `Status.RED` for a Care kind with no
Care Event ever logged, reasoning "never logged — treated as overdue, not 'no data'" — so a
brand-new Enclosure's Care section (and Dashboard pill) read as already delinquent before the user
had any chance to log anything. The new Care Setup Prompt (see CONTEXT.md) now actively nudges the
user to resolve this instead of leaving it to the pill color alone, which removes the original
reason for defaulting straight to Red.

**Decision**: a never-logged kind now reads `Status.UNKNOWN` (gray, "no data") instead of Red. Red
isn't dropped, though — Feeding and Watering are the actual actions this app exists to track, so a
kind still unlogged after the Care Setup Prompt has nagged about it on 3 separate calendar days
escalates to Red anyway, same "no data" pill text, just recolored. The count is tracked per kind,
incremented at most once per calendar day the Enclosure admin page is visited while that kind
remains unlogged, and becomes moot again the moment the kind gets its first real Care Event.

**Considered Options**: gray forever until logged (rejected — a kind nobody ever gets around to
logging would stay low-visual-priority indefinitely, defeating the point of color-coded staleness);
keep the original immediate-Red behavior and just bolt the prompt on top (rejected — pairing "no
data" with an already-red pill reads as already-failing before the user's had any chance to respond
to the prompt).

**Consequences**: `enclosure` needs 4 new per-kind nag-count columns plus a per-kind last-nagged
date to dedupe same-day visits; `care_interval_status()`'s signature grows to take the nag count;
the Dashboard's worst-status rollup (`dashboard.html`'s `severity` map) needs an `"unknown"` entry,
since it previously only ever saw green/yellow/red for a Care kind.
