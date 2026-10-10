// Sparkline (under a Reading's "as of" line) and Graphs page charts — both built on vendored
// Chart.js (web/static/chart.min.js; see CONTEXT.md: Sparkline, Graphs, Overlay; ADR 0022, ADR
// 0023). No date-adapter library is vendored alongside Chart.js: every x value is a plain epoch-ms
// number on a linear scale, with a tick callback formatting it for display, rather than Chart.js's
// own "time" scale (which requires one).

const GRAPH_PALETTE = ["#4f9d6e", "#4f8fd6", "#d6a24f", "#d65f5f", "#9d6ed6", "#5fd6c6", "#d64f9d", "#8fd64f"];
const SPARKLINE_COLOR = "#4f8fd6";

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

// A month of one Sensor metric's Readings under its "as of" line (see CONTEXT.md: Sparkline; ADR
// 0023) — still axis-less and legend-less, a glance-level shape rather than a full Graphs chart,
// but no longer fully non-interactive: a hover tooltip shows the exact day/value(s). A Smart
// Sensor's points are daily [epoch_ms, min, avg, max] bands (web/queries.py's _sparkline); a Manual
// Sensor's are raw [epoch_ms, value] pairs — detected here by point length rather than a separate
// data attribute, since a canvas's own points are always one shape or the other.
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
        // decimals) — Specific Gravity needs all 3 decimals (1.025-style) to mean anything;
        // hardcoding 2 here used to clip it. Defaults to 2 if the attribute's missing/invalid.
        const decimalsAttr = parseInt(canvas.dataset.decimals, 10);
        const precision = Number.isFinite(decimalsAttr) ? decimalsAttr : 2;
        let datasets;
        if (isBand) {
            // Same min/max band technique as buildGraphChart below: an invisible "min" line, then
            // a "max" line filled back to it, then the real average line drawn on top.
            datasets = [
                {data: points.map(function (p) { return {x: p[0], y: p[1]}; }),
                 borderWidth: 0, pointRadius: 0, fill: false, borderColor: "rgba(0,0,0,0)"},
                {data: points.map(function (p) { return {x: p[0], y: p[3]}; }),
                 borderWidth: 0, pointRadius: 0, fill: "-1", backgroundColor: SPARKLINE_COLOR + "2a", borderColor: "rgba(0,0,0,0)"},
                {data: points.map(function (p) { return {x: p[0], y: p[2]}; }),
                 borderColor: SPARKLINE_COLOR, borderWidth: 1.25, pointRadius: 0, fill: false, tension: 0.25},
            ];
        } else {
            datasets = [
                {data: points.map(function (p) { return {x: p[0], y: p[1]}; }),
                 borderColor: SPARKLINE_COLOR, borderWidth: 1.25, pointRadius: 0, fill: false, tension: 0.25},
            ];
        }
        new Chart(canvas, {
            type: "line",
            data: {datasets: datasets},
            options: {
                responsive: false,
                animation: false,
                interaction: {mode: "nearest", intersect: false},
                scales: {x: {type: "linear", display: false}, y: {display: false}},
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
            if (row.shape === "band") {
                // Classic Chart.js min/max band: an invisible "min" line, then a "max" line filled
                // back to it (fill: "-1"), then the real average line drawn on top.
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[1]}; }),
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: false, borderColor: "rgba(0,0,0,0)"});
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[3]}; }),
                               yAxisID: axisId, borderWidth: 0, pointRadius: 0, fill: "-1", backgroundColor: color + "2a",
                               borderColor: "rgba(0,0,0,0)"});
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[2]}; }),
                               yAxisID: axisId, borderColor: color, borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.2});
            } else {
                datasets.push({label: row.label, data: row.series.map(function (p) { return {x: p[0], y: p[1]}; }),
                               yAxisID: axisId, borderColor: color, borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.2});
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
                        label: function (context) {
                            const raw = context.raw;
                            if (raw && raw.eventLabel !== undefined) return context.dataset.label + ": " + raw.eventLabel;
                            return context.dataset.label + ": " + Math.round(raw.y * 100) / 100;
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
