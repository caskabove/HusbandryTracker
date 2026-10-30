# Help: a visual "what does this page show/do" reference, separate from the Guide

**Context**: `/guide` (ADR-less, predates this one, just `web/main.py`'s `guide()` route) already
renders `docs/USER_GUIDE.md` as HTML — a setup walkthrough ("how do I add my first Enclosure").
That's a different job from what was asked for here: a short, visual reference per main screen
(Dashboard, Rooms, Enclosures, Plugs, Sensors), each answering "what am I looking at, and what can
I do from here" with a sample screenshot, not "how do I get this screen into this state." Folding
the two together would make the Guide both longer and harder to scan for either purpose.

**Decision — a new, separate Help section, not a Guide section**: `/help` lists all 5 topics with
a one-line summary each; `/help/{slug}` is one topic's own page. A "Help" nav link sits next to
"Guide" in `_nav.html`. The Guide is untouched.

**Decision — Rooms/Enclosures and Plugs/Sensors stay 4 separate topics even though they're 2 live
admin pages**: `/admin/enclosures` ("Rooms and Enclosures") and `/admin` ("Plugs and Sensors") each
combine two concepts onto one screen, but a Room and an Enclosure (same for a Plug and a Sensor)
are different things with different jobs — writing them up together would mean explaining two
"what you'll see"/"what you can do" lists on one page, which defeats the point of keeping each
topic scannable. Dashboard, Rooms, Enclosures, Plugs, Sensors are 5 separate topics; a later topic
can reuse the same underlying screenshot a sibling topic uses (they're often the same screen),
cropped or captioned differently, without the two write-ups needing to match page-for-page.

**Decision — each topic's content is a standalone HTML fragment, not a Jinja template**:
`docs/help/{slug}.html` is plain HTML (no Jinja syntax, no page chrome) — a `<figure>` with the
screenshot, an intro paragraph, then "What you'll see" and "What you can do" bullet lists, the same
shape on every topic. `web/main.py`'s `help_topic()` route reads the file and hands it to a shared
`help.html` shell (header/nav + a `.guide-content`-styled box) as `content_html`, mirroring exactly
how `guide()` already hands `guide.html` its own `content_html` — except Help's fragment is
authored as literal HTML directly, with no Markdown round trip, since the content is meant to be
reusable on its own (e.g. pasted elsewhere) without this app's template syntax baked into it.

**Decision — the sample images are supplied by the user, not generated here**: this session has no
browser automation to screenshot the running app. Each fragment already points at
`web/static/images/help/{slug}.png`; until that file exists, the browser just shows the `<img>`'s
alt text in the same screenshot box — the page renders correctly either way, so writing the content
isn't blocked on capturing images, and dropping a PNG in later needs no code change.

**Consequences**: two new routes (`GET /help`, `GET /help/{slug}`, 404 on an unknown slug), two new
templates (`help.html`, `help_index.html`), 5 new content files (`docs/help/*.html`), a nav entry,
and `.help-content`/`.help-topic-*` CSS reusing `.guide-main`/`.guide-content`'s existing box
styling rather than duplicating it. No schema or data-layer change. `HELP_TOPICS` in `web/main.py`
is the one list that drives both the index and the slug→title/file lookup — adding a 6th topic
later means one new entry there plus its own content file, not a new code path.
