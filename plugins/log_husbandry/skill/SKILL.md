---
name: log_husbandry
description: Interprets a natural-language husbandry note ("fed Bob a large mouse and cleaned his water") into one or more Care Events (Feeding, Watering, Spot-clean, Deep-clean) and logs them to this Husbandry Tracker install. Use when the user describes care they just performed in plain language, inside a session working in a Husbandry Tracker repo.
---

<what-to-do>

This skill turns a sentence describing husbandry care into real Care Events logged into this
Husbandry Tracker install — see CONTEXT.md: Care Event, Care Event Plugin Event, Skill; ADR 0046
for the full design this implements. Follow these steps in order.

## 0. Find the install root

Resolve paths below relative to this Husbandry Tracker installation's root — the folder
containing `data/`, `db/`, and `web/` (normally the current working directory, or its nearest
ancestor that contains `data/registry/`). If you can't find one, stop and say so — this skill only
works inside a Husbandry Tracker checkout.

## 1. Read the Registry

Read `data/registry/log_husbandry.json`. It's a flat snapshot:

```json
{
  "rooms":      [{"id": 1, "name": "Reptile Room"}],
  "enclosures": [{"id": 5, "name": "Snake Rack 3", "room_id": 1}],
  "animals":    [{"id": 7, "name": "Bob", "enclosure_id": 5}]
}
```

If the file doesn't exist, tell the user: "I can't find the current Rooms/Enclosures/Animals list
yet — make sure Husbandry Tracker's Ingest process has run at least once since this Skill was
activated," and stop.

## 2. Parse the utterance into candidate events

One utterance can describe several events (e.g. "fed Bob a large mouse and cleaned his water" is
a Feeding *and* a Watering). Split it into one candidate per distinct action, each one of:

- **Feeding** — who/what was fed. Resolve the named Animal against `animals` (case-insensitive
  exact match only — no fuzzy/nickname matching). This is a Spot-feed (`animal_id` set). If the
  sentence instead feeds a whole Enclosure with no Animal named, resolve the Enclosure directly
  (`animal_id` stays unset) — but in practice almost every utterance names an Animal.
- **Watering / Spot-clean / Deep-clean** — always Enclosure-scoped, never Animal-scoped (see
  CONTEXT.md: Watering / Cleaning). A pronoun like "his water" or "her tank" still resolves to the
  Animal's **Enclosure** — `animal_id` is never set for these three kinds, even when the sentence
  names an Animal to get there. Make this explicit later in the confirmation summary (step 5) so
  the user isn't misled into thinking it's scoped to just that Animal.

For a Feeding, also extract (all optional — leave unset if the sentence doesn't say):
- `food`: the free-text description as said (e.g. "large mouse") — don't split size out
  separately, this app's own Feeding Detail fuses them (see CONTEXT.md: Feeding Detail).
- `count`: a number if stated, default to `1` if a single item was named with no count language
  ("a mouse" → 1), otherwise leave unset.
- `prey_state`: map informal words to the stored enum **before writing anything** —
  "frozen"/"frozen-thawed"/"thawed" → `frozen_thawed`; "live"/"alive" → `live`;
  "dry"/"pellet"/"pellets" → `dry`. Leave unset if nothing in the sentence maps to one of these.
- `result`: "refused"/"wouldn't eat"/"didn't eat" → `refused`; "accepted"/"ate it" → `accepted`.
  Leave unset if the sentence doesn't say.

## 3. Resolve names, asking when ambiguous

For each candidate event's Animal/Enclosure name:
- **No match**: ask the user directly, don't guess — e.g. "I don't see an Animal named 'Bob' —
  can you check the name?"
- **Multiple matches** (nothing stops two different Enclosures from each having an Animal with the
  same name): ask the user to disambiguate — e.g. "I found two Animals named Bob: one in Reef
  Tank, one in Snake Rack 3 — which one?"

Do this *before* the confirmation step below — don't present a summary with an unresolved or
wrongly-guessed entity in it.

## 4. Detect (and refuse) backdating

If the utterance mentions a date or relative time ("yesterday," "this morning," "on Tuesday"),
don't silently log it as happening now and don't guess a timestamp. Tell the user: "I can only log
this as happening right now — backdating isn't supported yet," and ask whether to proceed logging
it as "now" or skip that event. Every event this skill writes is stamped at the moment the user
confirms it, full stop.

## 5. One combined confirmation for the whole utterance

Show the user everything parsed from the sentence as a numbered list, in one message — not one
confirmation per event. Make the Enclosure-scoped kinds unambiguous, e.g.:

```
1. Feeding — Bob — large mouse, frozen-thawed (repeating last), accepted
2. Watering — Snake Rack 3 (Bob's Enclosure)
```

Wait for explicit confirmation ("yes," "log it," etc.) before writing anything. If the user wants
to change something, update the relevant event(s) and show the summary again.

## 6. Write one Inbox file per confirmed event

Only after confirmation. For each event, write a file to `data/inbox/care_event/` with this exact
envelope:

```json
{
  "schema_version": 1,
  "plugin": "log_husbandry",
  "kind": "care_event",
  "external_id": "animal:7",
  "observed_at": "2026-01-01 12:00:00",
  "payload": {
    "enclosure_id": 5,
    "animal_id": 7,
    "care_kind": "feeding",
    "food": "large mouse",
    "count": 1
  }
}
```

- `external_id` is `"animal:<id>"` for a Spot-feed, otherwise `"enclosure:<id>"` — a free-form
  scope reference (see CONTEXT.md: Log Event's own convention, reused here), not something Ingest
  actually parses.
- `observed_at` is the current moment, UTC, formatted exactly `"YYYY-MM-DD HH:MM:SS"` (no `T`, no
  timezone suffix) — get this from the system clock, not from anything in the sentence (step 4).
- `payload.care_kind` is one of `feeding`/`watering`/`spot_clean`/`deep_clean`.
- `payload.animal_id` is only present for a Spot-feed — omit it entirely for every other case.
- `food`/`count`/`prey_state`/`result` are Feeding-only — omit whichever ones step 2 left unset.
  Don't invent a value for them; Ingest fills in sensible defaults from the Enclosure's/Animal's
  own last Feeding when they're missing (see ADR 0046) — that's not this skill's job.
- `payload.note` (optional, any kind) — only if the sentence has something left over worth
  recording that doesn't fit the other fields.

**Write atomically**, matching every other half of this filesystem contract (see
`plugins/common.py`'s own `_atomic_write_json`): write the JSON to a `*.tmp` file first, then move
it into place — e.g. via the shell, not by relying on your file-writing tool's own atomicity:

```
mv data/inbox/care_event/log_husbandry__animal7__<unique>.json.tmp data/inbox/care_event/log_husbandry__animal7__<unique>.json
```

(On Windows, `move` or PowerShell's `Move-Item` works the same way.) `<unique>` just needs to not
collide with another file from the same run — a timestamp plus a short random suffix is enough.

## 7. Tell the user what happens next

This write is fire-and-forget — the Skill has no way to confirm the event actually landed (that's
the whole point of going through the Inbox instead of writing to the database directly: it still
works even if Husbandry Tracker isn't running right now). Say something like: "Logged — this will
apply the next time Husbandry Tracker's Ingest runs (within a few seconds if it's currently
running, otherwise next time it's started)." Don't imply it's already reflected on the dashboard.

</what-to-do>

<supporting-info>

## Why this doesn't just write to the database

This skill deliberately has no direct database access and never will — see ADR 0046. It needs to
keep working even when no Husbandry Tracker process is running at the moment a user talks to it;
writing straight to the database would break that the first time the app happens to be stopped.

## Scope (v1)

Only the four Care Event kinds (Feeding, Watering, Spot-clean, Deep-clean) — not Shed Log, Animal
Log, or Plant Health, and not backdating. Don't try to handle those; tell the user they're not
supported yet if asked.

</supporting-info>
