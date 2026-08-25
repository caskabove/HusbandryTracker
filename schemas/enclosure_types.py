"""Enclosure Type schema — the single source of truth for which Sensor Target Range metrics and
Plug Controller Kinds apply to which Enclosure Type (see CONTEXT.md: Enclosure Type; ADR 0011).

Enclosure Type decides which of `sensor`'s Target Range columns are relevant to that Enclosure's
Sensors, and which of a Plug's Controller Kinds make sense for it — both real, fixed columns in
db/schema.sql (not a runtime-configurable parameter table; see ADR 0011 for why), gated here in
code instead. This module is pure data + lookups — it never touches the database. web/admin_queries.py
calls into it to validate saves (reject a pH value on a Basic-type Enclosure); web/admin.py or its
templates call into it to decide which form fields to render.

Bioactive is deliberately NOT modeled here — it's independent of Enclosure Type (see CONTEXT.md:
Bioactive) and gates Plant/Plant Health tracking on its own, combinable with any of the four types
below. See plant_tracking_enabled() at the bottom.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# Must match the enclosure_type CHECK constraint in db/schema.sql.
ENCLOSURE_TYPES = ("basic", "freshwater", "saltwater", "amphibian")

ENCLOSURE_TYPE_LABELS = {
    "basic": "Basic (snake / lizard / tortoise / insect)",
    "freshwater": "Freshwater",
    "saltwater": "Saltwater",
    "amphibian": "Amphibian",
}


@dataclass(frozen=True)
class TargetRangeMetric:
    """One Sensor Target Range metric (see CONTEXT.md: Target Range) — a min/max column pair on
    `sensor`, plus which Enclosure Types it's relevant to."""
    key: str                          # stable id — form field names, validation error lookups
    label: str                        # human-readable, for Admin form labels
    unit: str                         # display unit; "" if unitless (pH)
    min_column: str                   # db/schema.sql column name
    max_column: str
    enclosure_types: tuple[str, ...]  # which Enclosure Types show/allow this metric
    converts_f_c: bool = False        # True only for Temperature — stored as Celsius, shown as F
                                       # (see web/admin.py's _f_to_c/_c_to_f)


# Ordered for display — core environmental metrics first, then water chemistry roughly in the
# order a test kit strip reads them. Ammonia/nitrite/nitrate/phosphate targets are usually just "as
# low as possible" (min left at 0) — still a real min/max pair for the same shape as every other
# metric (see db/schema.sql's comment on the sensor table).
TARGET_RANGE_METRICS: tuple[TargetRangeMetric, ...] = (
    TargetRangeMetric("temperature", "Temperature", "F",
                       "target_temp_min_c", "target_temp_max_c",
                       ENCLOSURE_TYPES, converts_f_c=True),
    TargetRangeMetric("humidity", "Humidity", "%",
                       "target_humidity_min", "target_humidity_max",
                       ("basic", "amphibian")),
    TargetRangeMetric("ph", "pH", "",
                       "target_ph_min", "target_ph_max",
                       ("freshwater", "saltwater", "amphibian")),
    TargetRangeMetric("ammonia", "Ammonia", "ppm",
                       "target_ammonia_ppm_min", "target_ammonia_ppm_max",
                       ("freshwater", "saltwater", "amphibian")),
    TargetRangeMetric("nitrite", "Nitrite", "ppm",
                       "target_nitrite_ppm_min", "target_nitrite_ppm_max",
                       ("freshwater", "saltwater", "amphibian")),
    TargetRangeMetric("nitrate", "Nitrate", "ppm",
                       "target_nitrate_ppm_min", "target_nitrate_ppm_max",
                       ("freshwater", "saltwater", "amphibian")),
    TargetRangeMetric("salinity", "Salinity", "ppt",
                       "target_salinity_ppt_min", "target_salinity_ppt_max",
                       ("saltwater",)),
    TargetRangeMetric("alkalinity", "Alkalinity", "dKH",
                       "target_alkalinity_dkh_min", "target_alkalinity_dkh_max",
                       ("saltwater",)),
    TargetRangeMetric("calcium", "Calcium", "ppm",
                       "target_calcium_ppm_min", "target_calcium_ppm_max",
                       ("saltwater",)),
    TargetRangeMetric("magnesium", "Magnesium", "ppm",
                       "target_magnesium_ppm_min", "target_magnesium_ppm_max",
                       ("saltwater",)),
    TargetRangeMetric("phosphate", "Phosphate", "ppm",
                       "target_phosphate_ppm_min", "target_phosphate_ppm_max",
                       ("saltwater",)),
)

_METRICS_BY_KEY = {m.key: m for m in TARGET_RANGE_METRICS}

# Which Controller Kinds make sense per Enclosure Type — see CONTEXT.md: Controller Kind, ADR 0008.
# 'none' is always allowed everywhere (the common case: the Plug powers the source directly).
# Hydrostat-Controlled (a humidity setpoint) isn't meaningful for a fully-submerged aquarium — a
# Freshwater/Saltwater tank has no ambient-humidity concept, only water.
_CONTROLLER_KINDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "basic": ("none", "thermostat", "hydrostat"),
    "freshwater": ("none", "thermostat"),
    "saltwater": ("none", "thermostat"),
    "amphibian": ("none", "thermostat", "hydrostat"),
}


def _check_enclosure_type(enclosure_type: str) -> None:
    if enclosure_type not in ENCLOSURE_TYPES:
        raise ValueError(f"Unknown Enclosure Type: {enclosure_type!r}")


def target_range_metrics_for(enclosure_type: str) -> tuple[TargetRangeMetric, ...]:
    """All Target Range metrics relevant to this Enclosure Type, in display order."""
    _check_enclosure_type(enclosure_type)
    return tuple(m for m in TARGET_RANGE_METRICS if enclosure_type in m.enclosure_types)


def is_metric_applicable(enclosure_type: str, metric_key: str) -> bool:
    _check_enclosure_type(enclosure_type)
    metric = _METRICS_BY_KEY.get(metric_key)
    if metric is None:
        raise ValueError(f"Unknown Target Range metric: {metric_key!r}")
    return enclosure_type in metric.enclosure_types


def allowed_controller_kinds(enclosure_type: str) -> tuple[str, ...]:
    """Which Plug controller_kind values are meaningful for a Plug serving this Enclosure Type."""
    _check_enclosure_type(enclosure_type)
    return _CONTROLLER_KINDS_BY_TYPE[enclosure_type]


def is_controller_kind_allowed(enclosure_type: str, controller_kind: str) -> bool:
    return controller_kind in allowed_controller_kinds(enclosure_type)


def validate_target_ranges(enclosure_type: str, provided_metric_keys: Iterable[str]) -> None:
    """Raise ValueError (a friendly message, matching web/admin_queries.py's pattern — see
    CONTEXT.md: Manual Sensor's Target Range rule) if any of the given metric keys don't apply to
    this Enclosure Type. `provided_metric_keys` should only be metrics that actually have a min or
    max value set on the save being validated — a caller shouldn't flag ones left blank."""
    _check_enclosure_type(enclosure_type)
    bad = [key for key in provided_metric_keys if not is_metric_applicable(enclosure_type, key)]
    if bad:
        bad_labels = ", ".join(_METRICS_BY_KEY[key].label for key in bad)
        verb = "is" if len(bad) == 1 else "are"
        raise ValueError(
            f"{bad_labels} {verb} not relevant to a {ENCLOSURE_TYPE_LABELS[enclosure_type]} Enclosure."
        )


def plant_tracking_enabled(bioactive: bool) -> bool:
    """Plant/Plant Health tracking is gated by Bioactive, not Enclosure Type — see CONTEXT.md:
    Bioactive, Plant. Combinable with any Enclosure Type, so this takes the flag directly rather
    than an enclosure_type."""
    return bool(bioactive)


if __name__ == "__main__":
    # Quick manual sanity check — print what each Enclosure Type actually exposes.
    for etype in ENCLOSURE_TYPES:
        metrics = ", ".join(m.label for m in target_range_metrics_for(etype))
        kinds = ", ".join(allowed_controller_kinds(etype))
        print(f"{ENCLOSURE_TYPE_LABELS[etype]}:")
        print(f"  Target Range metrics: {metrics}")
        print(f"  Controller Kinds: {kinds}")
