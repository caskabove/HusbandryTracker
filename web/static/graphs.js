// Sparkline (under a Reading's "as of" line) and Graphs page charts — both built on vendored
// Chart.js (web/static/chart.min.js; see CONTEXT.md: Sparkline, Graphs, Overlay; ADR 0022, ADR
// 0023). No date-adapter library is vendored alongside Chart.js: every x value is a plain epoch-ms
// number on a linear scale, with a tick callback formatting it for display, rather than Chart.js's
// own "time" scale (which requires one).

const GRAPH_PALETTE = ["#4f9d6e", "#4f8fd6", "#d6a24f", "#d65f5f", "#9d6ed6", "#5fd6c6", "#d64f9d", "#8fd64f"];
const SPARKLINE_COLOR = "#007f7f";
const SPARKLINE_TARGET_RANGE_COLOR = "#4caf72"; // var(--status-green) — canvas fills can't read CSS vars
const SPARKLINE_AXIS_COLOR = "#93a89c"; // var(--text-muted)

function formatGraphTick(value) {
    const d = new Date(value);
    return d.toLocaleString(undefined, {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
}

function formatSparklineDate(value) {
    const d = new Date(value);
    return d.toLocaleDateString(undefined, {month: "short", day: "numeric"});
}

function sparklineIsRealDataset(item) {
    return item.dataset.borderWidth !== 0;
}



// A week or month (viewer's pick — see setSparklineRange below) of one Sensor metric's Readings
// under its "as of" line (see CONTEXT.md: Sparkline; ADR 0023, ADR 0024, ADR 0028, ADR 0032) — a
// compact preview of the same metric's Graphs chart rather than a plain glance glyph: a minimal
// time/value axis, a shaded Target Range band (when the Sensor has one set) behind the metric's
// own data, and a hover tooltip. A Smart Sensor's points are a 3-day-smoothed daily [epoch_ms,
// min, avg, max] band (web/queries.py's _sparkline); a Manual Sensor's are raw, unsmoothed
// [epoch_ms, value] pairs — detected here by point length rather than a separate data attribute,
// since a canvas's own points are always one shape or the other.
//
// Both windows' points are already embedded on the canvas (data-points-week/data-points-month —
// web/queries.py fetches both up front), so switching windows is a pure client-side redraw, no
// request. canvas.dataset.range tracks which one is currently showing; renderSparkline reads it
// and (re)builds the Chart.js instance, destroying any previous one first since Chart.js refuses
// to reuse a canvas that already has a live chart on it.
function renderSparkline(canvas) {
    if (typeof Chart === "undefined") return;
    const range = canvas.dataset.range === "month" ? "month" : "week";
    let points;
    try {
        points = JSON.parse(canvas.dataset[range === "month" ? "pointsMonth" : "pointsWeek"] || "[]");
    } catch (e) {
        points = [];
    }
    if (canvas._sparklineChart) {
        canvas._sparklineChart.destroy();
        canvas._sparklineChart = null;
    }
    const titleAttr = canvas.dataset[range === "month" ? "titleMonth" : "titleWeek"];
    if (titleAttr) canvas.title = titleAttr;
    if (points.length === 0) return;
    renderSparklineChart(canvas, points);
}

function setSparklineRange(button, range) {
    const chartWrap = button.closest(".sparkline-chart");
    if (!chartWrap) return;
    chartWrap.querySelectorAll(".sparkline-range-btn").forEach(function (b) {
        b.classList.toggle("active", b === button);
    });
    const canvas = chartWrap.querySelector("canvas.sparkline");
    if (!canvas) return;
    canvas.dataset.range = range;
    renderSparkline(canvas);
}

function renderSparklineChart(canvas, points) {
    const isBand = points[0].length === 4;
    // Each metric's own display precision (see schemas/enclosure_types.py's TargetRangeMetric.
    // decimals) — Specific Gravity needs all 3 decimals (1.025-style) to mean anything.
    // Defaults to 2 if the attribute's missing/invalid.
    const decimalsAttr = parseInt(canvas.dataset.decimals, 10);
    const precision = Number.isFinite(decimalsAttr) ? decimalsAttr : 2;
    const targetMin = parseFloat(canvas.dataset.targetMin);
    const targetMax = parseFloat(canvas.dataset.targetMax);
    const hasTargetRange = Number.isFinite(targetMin) && Number.isFinite(targetMax);
    // pH's day/night band (ADR 0037) — same [epoch_ms, morning, afternoon, night] band shape as a
    // Smart Sensor's min/avg/max, just with Period Slot identity instead of statistics behind the
    // three values, so the tooltip below names them instead of saying "range"/"avg".
    const slotBand = canvas.dataset.slotBand === "1";

    const firstX = points[0][0];
    const lastX = points[points.length - 1][0];
    const datasets = [];

    // Target Range band (ADR 0024) — drawn first so the metric's own data band/line below
    // renders on top of it, same invisible-min/filled-max technique as the data band itself,
    // just flat across the chart's whole x-range instead of varying with time.
    if (hasTargetRange) {
        datasets.push({data: [{x: firstX, y: targetMin}, {x: lastX, y: targetMin}],
                       borderWidth: 0, pointRadius: 0, fill: false, borderColor: "rgba(0,0,0,0)"});
        datasets.push({data: [{x: firstX, y: targetMax}, {x: lastX, y: targetMax}],
                       borderWidth: 0, pointRadius: 0, fill: "-1",
                       backgroundColor: SPARKLINE_TARGET_RANGE_COLOR + "26", borderColor: "rgba(0,0,0,0)"});
    }

    if (isBand) {
        // Same min/max band technique as buildGraphChart below: an invisible "min" line, then
        // a "max" line filled back to it, then the real (already 3-day-smoothed) average line
        // drawn on top of everything, including the Target Range band above.
        datasets.push({data: points.map(function (p) { return {x: p[0], y: p[1]}; }),
                       borderWidth: 0, pointRadius: 0, fill: false, borderColor: "rgba(0,0,0,0)"});
        datasets.push({data: points.map(function (p) { return {x: p[0], y: p[3]}; }),
                       borderWidth: 0, pointRadius: 0, fill: "-1", backgroundColor: SPARKLINE_COLOR + "2a", borderColor: "rgba(0,0,0,0)"});
        datasets.push({data: points.map(function (p) { return {x: p[0], y: p[2]}; }),
                       borderColor: SPARKLINE_COLOR, borderWidth: 2, pointRadius: 0, fill: false, tension: 0.25});
    } else {
        datasets.push({data: points.map(function (p) { return {x: p[0], y: p[1]}; }),
                       borderColor: SPARKLINE_COLOR, borderWidth: 2, pointRadius: 0, fill: false, tension: 0.25});
    }

    // y-scale anchors to the Target Range when set (ties the axis to the shaded band) but
    // always expands to cover the actual data too — an out-of-range Reading, the one thing the
    // Out of Target Range Alert Condition exists to catch, is never clipped off-chart just to
    // keep the scale stable (see ADR 0024).
    const allValues = [];
    points.forEach(function (p) {
        for (let i = 1; i < p.length; i++) allValues.push(p[i]);
    });
    let yMin = Math.min.apply(null, allValues);
    let yMax = Math.max.apply(null, allValues);
    if (hasTargetRange) {
        yMin = Math.min(yMin, targetMin);
        yMax = Math.max(yMax, targetMax);
    }
    const pad = (yMax - yMin) * 0.08 || Math.pow(10, -precision);
    yMin -= pad;
    yMax += pad;

    canvas._sparklineChart = new Chart(canvas, {
        type: "line",
        data: {datasets: datasets},
        options: {
            responsive: false,
            animation: false,
            interaction: {mode: "nearest", intersect: false},
            scales: {
                // A few date/value labels, no gridlines — kept sparse so this still reads as a
                // compact preview rather than a second full Graphs chart (ADR 0024). The x-axis
                // shows exactly the window's start and end date (ADR 0028), not Chart.js's own
                // "nice" auto-picked ticks, since a week-long sparkline has little room for more.
                x: {
                    type: "linear",
                    grid: {display: false},
                    ticks: {font: {size: 9}, color: SPARKLINE_AXIS_COLOR, callback: formatSparklineDate},
                    afterBuildTicks: function (axis) {
                        axis.ticks = firstX === lastX ? [{value: firstX}] : [{value: firstX}, {value: lastX}];
                    },
                },
                y: {
                    min: yMin,
                    max: yMax,
                    grid: {display: false},
                    ticks: {
                        maxTicksLimit: 3, font: {size: 9}, color: SPARKLINE_AXIS_COLOR,
                        callback: function (value) { return value.toFixed(precision); },
                    },
                },
            },
            plugins: {
                legend: {display: false},
                tooltip: {
                    filter: sparklineIsRealDataset,
                    callbacks: {
                        title: function (items) {
                            return items.length ? formatSparklineDate(items[0].parsed.x) : "";
                        },
                        label: function (context) {
                            const p = points[context.dataIndex];
                            if (isBand && slotBand) {
                                return "Afternoon " + p[2].toFixed(precision) +
                                    " (Morning " + p[1].toFixed(precision) + " – Night " + p[3].toFixed(precision) + ")";
                            }
                            if (isBand) {
                                return "avg " + p[2].toFixed(precision) +
                                    " (range " + p[1].toFixed(precision) + "–" + p[3].toFixed(precision) + ")";
                            }
                            return p[1].toFixed(precision);
                        },
                    },
                },
            },
        },
    });
}

function initSparklines() {
    if (typeof Chart === "undefined") return;
    document.querySelectorAll("canvas.sparkline").forEach(renderSparkline);
}

// One Y-axis per distinct unit among a chart's numeric ("line") rows, assigned in first-seen
// order and alternated left/right — see CONTEXT.md: Overlay ("numeric rows sharing a unit share
// one Y-axis; a row with a different unit gets its own").
function axisIdForUnit(unitAxisIds, unit) {
    const key = unit || "—";
    if (!unitAxisIds.has(key)) {
        unitAxisIds.set(key, "y" + unitAxisIds.size);
    }
    return unitAxisIds.get(key);
}

// A row's own hidden min/max helper datasets carry borderWidth 0 so the legend (and this filter)
// can tell them apart from the one real, visible dataset each line row contributes.
function isRealDataset(item, data) {
    return data.datasets[item.datasetIndex].borderWidth !== 0;
}

// The chart-wide x domain (across every row's series, line or marker) — a row's Target Range band
// (see below) is flat across the whole visible window, so it needs the same two x endpoints every
// other row's data spans, not just its own row's range.
function seriesXExtent(rows) {
    let first = Infinity, last = -Infinity;
    rows.forEach(function (row) {
        row.series.forEach(function (p) {
            if (p[0] < first) first = p[0];
            if (p[0] > last) last = p[0];
        });
    });
    return [first, last];
}

// At least 2 of a metric's own units above/below its Target Range (see CONTEXT.md: Target Range;
// ADR 0035) — never less, but never clipped tighter than the real data either (an out-of-range
// Reading, the one thing the Out of Target Range Alert Condition exists to catch, must stay
// visible), same "pad the Target Range, then still expand to data" rule Sparkline already uses
// (ADR 0024, graphs.js's renderSparklineChart). A metric whose values sit far below 2 (Specific
// Gravity, ~1.02) overrides this flat default via its own row.target_pad/tick_step (ADR 0036) —
// see the axisExtent loop below.
const TARGET_RANGE_AXIS_PAD = 2;

function buildGraphChart(canvas, rows) {
    const unitAxisIds = new Map();
    const scales = {
        x: {
            type: "linear",
            ticks: {callback: formatGraphTick, autoSkip: true, maxRotation: 0},
        },
    };
    const [firstX, lastX] = seriesXExtent(rows);
    // Per-axis running extent, so an axis gets an explicit min/max only when at least one of its
    // rows actually has a Target Range — an axis with none keeps today's plain Chart.js auto-scale.
    const axisExtent = new Map();
    const datasets = [];
    rows.forEach(function (row, index) {
        const color = GRAPH_PALETTE[index % GRAPH_PALETTE.length];
        if (row.chart_type === "line") {
            const axisId = axisIdForUnit(unitAxisIds, row.unit);

            if (!scales[axisId]) {
                scales[axisId] = {
                    position: (unitAxisIds.size - 1) % 2 === 0 ? "left" : "right",
                    title: {display: Boolean(row.unit), text: row.unit || ""},
                    grid: {drawOnChartArea: unitAxisIds.size === 1},
                };
            }
            const hasTargetRange = row.target_min != null && row.target_max != null;
            if (hasTargetRange) {
                if (!axisExtent.has(axisId)) axisExtent.set(axisId, {});
                const extent = axisExtent.get(axisId);
                extent.targetMin = extent.targetMin === undefined ? row.target_min : Math.min(extent.targetMin, row.target_min);
                extent.targetMax = extent.targetMax === undefined ? row.target_max : Math.max(extent.targetMax, row.target_max);
                // A metric whose values sit far below 2 (Specific Gravity, ~1.02) overrides the
                // flat default pad/ticks via its own axis_pad/step (ADR 0036) — otherwise every
                // row on this axis shares the same metric anyway, so the last one wins.
                if (row.target_pad != null) extent.pad = row.target_pad;
                if (row.tick_step != null) extent.tickStep = row.tick_step;
                // Drawn before the row's own dataset(s) below, same "band first, data on top"
                // ordering Sparkline uses — also keeps each dataset's fill: "-1" pointed at the
                // sibling pushed just before it, rather than accidentally filling back to this
                // row's own average/raw line instead.
                datasets.push({label: row.label, data: [{x: firstX, y: row.target_min}, {x: lastX, y: row.target_min}],
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: false, borderColor: "rgba(0,0,0,0)"});
                datasets.push({label: row.label, data: [{x: firstX, y: row.target_max}, {x: lastX, y: row.target_max}],
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: "-1",
                               backgroundColor: color + "26", borderColor: "rgba(0,0,0,0)"});
            }
            // decimals rides along on the dataset itself (not just the row) so the tooltip label
            // callback below — which only ever sees one dataset at a time — knows how many digits
            // this particular row's values need (see graphs_queries.py's module docstring).
            const decimals = Number.isFinite(row.decimals) ? row.decimals : 2;
            const rowValues = [];
            row.series.forEach(function (p) { for (let i = 1; i < p.length; i++) rowValues.push(p[i]); });
            if (rowValues.length) {
                if (!axisExtent.has(axisId)) axisExtent.set(axisId, {});
                const extent = axisExtent.get(axisId);
                const rowMin = Math.min.apply(null, rowValues), rowMax = Math.max.apply(null, rowValues);
                extent.dataMin = extent.dataMin === undefined ? rowMin : Math.min(extent.dataMin, rowMin);
                extent.dataMax = extent.dataMax === undefined ? rowMax : Math.max(extent.dataMax, rowMax);
            }
            if (row.shape === "band") {
                // Classic Chart.js min/max band: an invisible "min" line, then a "max" line filled
                // back to it (fill: "-1"), then the real average line drawn on top. row.slot_labels
                // (pH's day/night band — ADR 0037) names these three by Period Slot identity
                // instead of statistics, so the tooltip says "Morning"/"Afternoon"/"Night" instead
                // of a bare value — every other band row keeps the plain shared label.
                const bottomLabel = row.slot_labels ? row.label + " — " + row.slot_labels[0] : row.label;
                const topLabel = row.slot_labels ? row.label + " — " + row.slot_labels[2] : row.label;
                const midLabel = row.slot_labels ? row.label + " — " + row.slot_labels[1] : row.label;
                datasets.push({label: bottomLabel, data: row.series.map(function (p) { return {x: p[0], y: p[1]}; }),
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: false, borderColor: "rgba(0,0,0,0)", decimals: decimals});
                datasets.push({label: topLabel, data: row.series.map(function (p) { return {x: p[0], y: p[3]}; }),
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: "-1", backgroundColor: color + "2a",
                               borderColor: "rgba(0,0,0,0)", decimals: decimals});
                datasets.push({label: midLabel, data: row.series.map(function (p) { return {x: p[0], y: p[2]}; }),
                               yAxisID: axisId, borderColor: color, borderWidth: 2, pointRadius: 0, fill: false, tension: 0.2, decimals: decimals});
            } else {
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[1]}; }),
                               yAxisID: axisId, borderColor: color, borderWidth: 2, pointRadius: 0, fill: false, tension: 0.2, decimals: decimals});
            }
        } else {
            // A marker row (Care Event / Plug Status / Animal Condition) has a moment but no
            // Y-value of its own — pinned to a fixed point on a shared, hidden axis instead of a
            // real scale (see CONTEXT.md: Graphs, Overlay).
            if (!scales.events) {
                scales.events = {min: 0, max: 2, display: false};
            }
            datasets.push({
                type: "scatter",
                label: row.label,
                data: row.series.map(function (p) { return {x: p[0], y: 1, eventLabel: p[1]}; }),
                yAxisID: "events",
                showLine: false,
                pointStyle: "circle",
                pointRadius: 5,
                pointHoverRadius: 7,
                backgroundColor: color,
                borderColor: color,
            });
        }
    });

    // Apply the padded min/max to every axis that had at least one row with a Target Range —
    // an axis with none is left alone, keeping today's plain Chart.js auto-scale.
    axisExtent.forEach(function (extent, axisId) {
        if (extent.targetMin === undefined) return;
        // No real data yet on this axis (e.g. a Target Range set before any Reading is logged) —
        // fall back to just the padded Target Range itself rather than Math.min/max-ing against
        // an undefined dataMin/dataMax, which would otherwise poison the axis with NaN.
        const dataMin = extent.dataMin === undefined ? extent.targetMin : extent.dataMin;
        const dataMax = extent.dataMax === undefined ? extent.targetMax : extent.dataMax;
        const pad = extent.pad != null ? extent.pad : TARGET_RANGE_AXIS_PAD;
        scales[axisId].min = Math.min(dataMin, extent.targetMin - pad);
        scales[axisId].max = Math.max(dataMax, extent.targetMax + pad);
        // Tick the axis in exact steps instead of auto-picking "nice" numbers — only set when the
        // metric overrode its pad too (ADR 0036); every other axis keeps its normal auto ticks.
        if (extent.tickStep != null) {
            scales[axisId].ticks = Object.assign({}, scales[axisId].ticks, {stepSize: extent.tickStep});
        }
    });

    return new Chart(canvas, {
        type: "line",
        data: {datasets: datasets},

        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {mode: "nearest", intersect: false},
            scales: scales,
            plugins: {

                legend: {display: datasets.length > 1, labels: {filter: isRealDataset}},
                tooltip: {
                    callbacks: {
                        title: function (items) {
                            return items.length ? formatGraphTick(items[0].parsed.x) : "";
                        },
                        label: function (context) {
                            const raw = context.raw;
                            if (raw && raw.eventLabel !== undefined) return context.dataset.label + ": " + raw.eventLabel;
                            const decimals = Number.isFinite(context.dataset.decimals) ? context.dataset.decimals : 2;
                            return context.dataset.label + ": " + raw.y.toFixed(decimals);
                        },
                    },
                },
            },
        },
    });
}

function initGraphCharts() {
    if (typeof Chart === "undefined") return;
    document.querySelectorAll("canvas.graph-canvas").forEach(function (canvas) {
        let rows;
        try {
            rows = JSON.parse(canvas.dataset.chart || "[]");
        } catch (e) {
            return;
        }
        if (rows.length === 0 || !rows.some(function (row) { return row.series.length > 0; })) return;
        buildGraphChart(canvas, rows);
    });
}

// Enlarged chart view (see CONTEXT.md: Graphs) — one shared <dialog>, re-filled from whichever
// card's own already-rendered canvas the clicked button points at (its data-chart JSON, already
// on the page — enlarging never needs a round trip). The modal's own chart is a second, separate
// Chart.js instance on its own canvas, not a CSS zoom of the small one, rebuilt fresh every open
// and destroyed on close (a canvas can't be reused by a second live Chart.js instance).
let graphModalChart = null;

function closeGraphModal() {
    if (graphModalChart) {
        graphModalChart.destroy();
        graphModalChart = null;
    }
    const dialog = document.getElementById("graph-modal");
    if (dialog && dialog.open) dialog.close();
}

function openGraphModal(button) {
    if (typeof Chart === "undefined") return;
    const target = document.getElementById(button.dataset.target);
    const sourceCanvas = target ? target.querySelector("canvas.graph-canvas") : null;
    if (!sourceCanvas) return;
    let rows;
    try {
        rows = JSON.parse(sourceCanvas.dataset.chart || "[]");
    } catch (e) {
        return;
    }
    const dialog = document.getElementById("graph-modal");
    const heading = target.querySelector("h2, h3");
    document.getElementById("graph-modal-title").textContent = heading ? heading.firstChild.textContent.trim() : "";
    if (graphModalChart) {
        graphModalChart.destroy();
        graphModalChart = null;
    }
    dialog.showModal();
    graphModalChart = buildGraphChart(document.getElementById("graph-modal-canvas"), rows);
}

document.addEventListener("DOMContentLoaded", function () {
    initSparklines();
    initGraphCharts();
    const modal = document.getElementById("graph-modal");
    if (modal) {
        modal.addEventListener("close", closeGraphModal);
        // A click directly on the <dialog> element itself (not anything inside it) landed on the
        // ::backdrop — dismiss like clicking outside any other modal.
        modal.addEventListener("click", function (e) {
            if (e.target === modal) closeGraphModal();
        });
    }
});
