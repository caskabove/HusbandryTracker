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



// A week of one Sensor metric's Readings under its "as of" line (see CONTEXT.md: Sparkline; ADR
// 0023, ADR 0024, ADR 0028) — a compact preview of the same metric's Graphs chart rather than a plain glance
// glyph: a minimal time/value axis, a shaded Target Range band (when the Sensor has one set) behind
// the metric's own data, and a hover tooltip. A Smart Sensor's points are a 3-day-smoothed daily
// [epoch_ms, min, avg, max] band (web/queries.py's _sparkline); a Manual Sensor's are raw, unsmoothed
// [epoch_ms, value] pairs — detected here by point length rather than a separate data attribute,
// since a canvas's own points are always one shape or the other.
function initSparklines() {
    if (typeof Chart === "undefined") return;
    document.querySelectorAll("canvas.sparkline").forEach(function (canvas) {
        let points;
        try {
            points = JSON.parse(canvas.dataset.points || "[]");
        } catch (e) {
            return;
        }
        if (points.length === 0) return;
        const isBand = points[0].length === 4;
        // Each metric's own display precision (see schemas/enclosure_types.py's TargetRangeMetric.
        // decimals) — Specific Gravity needs all 3 decimals (1.025-style) to mean anything.
        // Defaults to 2 if the attribute's missing/invalid.
        const decimalsAttr = parseInt(canvas.dataset.decimals, 10);
        const precision = Number.isFinite(decimalsAttr) ? decimalsAttr : 2;
        const targetMin = parseFloat(canvas.dataset.targetMin);
        const targetMax = parseFloat(canvas.dataset.targetMax);
        const hasTargetRange = Number.isFinite(targetMin) && Number.isFinite(targetMax);

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

        new Chart(canvas, {
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
    });
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

function buildGraphChart(canvas, rows) {
    const unitAxisIds = new Map();
    const scales = {
        x: {
            type: "linear",
            ticks: {callback: formatGraphTick, autoSkip: true, maxRotation: 0},
        },
    };
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
            // decimals rides along on the dataset itself (not just the row) so the tooltip label
            // callback below — which only ever sees one dataset at a time — knows how many digits
            // this particular row's values need (see graphs_queries.py's module docstring).
            const decimals = Number.isFinite(row.decimals) ? row.decimals : 2;
            if (row.shape === "band") {
                // Classic Chart.js min/max band: an invisible "min" line, then a "max" line filled
                // back to it (fill: "-1"), then the real average line drawn on top.
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[1]}; }),
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: false, borderColor: "rgba(0,0,0,0)", decimals: decimals});
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[3]}; }),
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: "-1", backgroundColor: color + "2a",
                               borderColor: "rgba(0,0,0,0)", decimals: decimals});
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[2]}; }),
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

    new Chart(canvas, {
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

document.addEventListener("DOMContentLoaded", function () {
    initSparklines();
    initGraphCharts();
});
