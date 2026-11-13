# Retire Ammonia/Nitrite; Freshwater gains KH, TDS and Phosphate

**Status**: accepted (RHA-115)

**Context**: ADR 0011 gave every water-type Enclosure Ammonia, Nitrite and Nitrate as Target Range
metrics. In practice Ammonia and Nitrite read 0 in any cycled tank and are only ever hand-entered,
so they added form fields without telling the keeper anything. Freshwater, meanwhile, was missing
the readings freshwater keepers actually take: KH, TDS (Total Dissolved Solids) and Phosphate.

**Decision**:

- **Ammonia and Nitrite are retired on every Enclosure Type** (Freshwater, Saltwater, Amphibian).
  They are **hidden in code, not dropped**: they move from `TARGET_RANGE_METRICS` to a separate
  `RETIRED_TARGET_RANGE_METRICS` tuple in `schemas/enclosure_types.py`. Their `sensor` and
  `sensor_reading` columns stay. They have to leave the main tuple, not just get an empty
  `enclosure_types`: `web/admin_queries.py` writes every metric in that tuple on each Sensor save,
  which would overwrite an older install's values with NULL. Bringing one back means moving its
  entry back and re-adding its Form params in `web/admin.py`/`web/main.py`.
- **KH reuses the existing `alkalinity_dkh` metric.** Carbonate hardness and reef "alkalinity" are
  the same dKH reading, so it is relabeled **"KH" everywhere** (the key and columns keep the
  `alkalinity` name) and enabled for Freshwater as well as Saltwater.
- **TDS is a new metric**, Freshwater only. It uses ppm, step 1, 0 decimals and slow default
  Volatility. Migration 30 adds `sensor.target_tds_ppm_min/max`, `sensor.volatility_tds` and
  `sensor_reading.tds_ppm`. It is not offered on Saltwater, where seawater's ~35,000 ppm TDS says
  nothing that salinity/SG don't already. Reef keepers test TDS on RO/DI water, not the tank.
- **Phosphate** is now on Freshwater and Saltwater.
- **Amphibian** keeps a lean set: Temperature, Humidity, UVB, pH, Nitrate.
- **Display order** (global): Temperature, Humidity, UVB, pH, KH, TDS, NO₃, SG, Salinity, Ca, Mg,
  Phosphate.
- **Species Knowledge Base** follows suit. The fish profiles' Ammonia/Nitrite target fields are
  hidden (columns kept), and Saltwater Inverts' "Alkalinity" becomes "KH". TDS and Phosphate fields
  for KB profiles are out of scope.

**Consequences**:

- An install that already logged Ammonia/Nitrite keeps that data in the database, but the
  Dashboard, Graphs and View Data no longer show it. There is no legacy view, and none is planned.
- The dormant columns are intentional. Don't "clean them up" with a table rebuild.
