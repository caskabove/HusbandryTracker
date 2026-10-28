# Graphs: an expand button opens any chart in a larger modal

**Context**: Graphs lays its charts out in a grid (`.graphs-grid`, `minmax(20rem, 1fr)` columns,
`14rem` tall — `20rem` for Overlay) so many rows fit on screen at once. That's the right default
density, but it means every chart is too small to read closely — there was no way to see one at a
size worth studying without the browser's own zoom, which just as readily resizes the whole page
around it.

**Decision — one shared `<dialog>`, rebuilt from the clicked card's own already-embedded data, not
a second request**: every chart card (each row's own, and Overlay) already carries its full row
JSON in its canvas's `data-chart` attribute for `buildGraphChart` to read. A new small "expand"
button next to each card's heading (`graph-expand-btn`) calls `openGraphModal(this)`, which reads
that same JSON straight off the card's canvas and feeds it to a second `buildGraphChart` call
against a canvas inside a single shared `<dialog id="graph-modal">` — enlarging is instant and
needs nothing from the server. The button carries a `data-target` pointing at its card's `id`
(every row card already has one — `row.key`, reused from ADR 0024's Sparkline click-through
anchors; Overlay's own section gained an `id="overlay-chart"` for the same purpose) rather than
relying on DOM nesting, so the same `openGraphModal` works for both shapes without special-casing
Overlay.

**Decision — a native `<dialog>`, not a hand-rolled overlay**: this app has had no modal of any
kind before now. `<dialog>`'s `showModal()` gets a real top-layer modal, a `::backdrop`, and
Escape-to-close for free; only backdrop-click-to-dismiss needed a few lines (`click` on the
`dialog` element itself, rather than anything inside it, is exactly a backdrop click). No new
dependency, no reimplementing focus-trapping by hand.

**Decision — the modal's chart is a second, separate Chart.js instance, destroyed on every
close**: a canvas can't host two live Chart.js instances, and the small card's own chart stays
mounted and interactive the whole time the modal is open (no need to tear it down). The modal's
own chart is created fresh on each open (`buildGraphChart` now returns its `Chart` instance so it
can be captured) and destroyed on close — both the explicit close button and the `dialog`'s native
`close` event (which also fires for Escape) route through the same cleanup, so there's one place a
leaked instance could ever come from, not three.

**Consequences**: no backend change — this is template/CSS/JS only. `graphs.html` gains one
`<dialog>` and a button per card; `graphs.js` gains ~25 lines (`openGraphModal`/`closeGraphModal`)
and now returns the `Chart` instance from `buildGraphChart` (harmless — every existing call site
already ignored the return value). `style.css` gains the modal's and button's own rules, sized at
`min(92vw, 1100px)` by `min(88vh, 720px)` — large enough to read, never larger than the viewport.
