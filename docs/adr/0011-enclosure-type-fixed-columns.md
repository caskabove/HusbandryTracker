# Enclosure Type gates real, fixed Target Range columns instead of a generic parameter system

**Status**: accepted

Reptile/insect Enclosures only ever need temp+humidity; aquatic setups need pH, salinity,
ammonia/nitrite/nitrate, and other water-chemistry parameters a reptile Enclosure never touches,
and Saltwater's list is larger again than Freshwater's. Considered a generic
`parameter_definition` + key-value-shaped reading/target-range system so a brand-new metric could
be added later without a schema migration — rejected as inconsistent with how this schema handles
everything else: plain nullable columns throughout, with `app_setting`'s own comment explicitly
rejecting a generic key-value shape "ahead of actually needing a second one." Purpose (on `plug`)
is the one deliberate free-text exception, and that was justified explicitly by genuinely unbounded,
low-cardinality-per-row values — not a precedent for parameters, which are a known, enumerable set.

Decision: `enclosure` gains a required `enclosure_type` column (`basic` | `freshwater` | `saltwater`
| `amphibian`); `sensor` grows real nullable columns for each new metric as it's actually needed.
A single Python module (`schemas/enclosure_types.py`-shaped) is the source of truth for which
columns/fields apply to which Enclosure Type, driving both the Admin form (which fields are shown)
and save-time validation (reject a pH value on a `basic`-type Enclosure) — the same pattern
`web/admin_queries.py` already uses to enforce the Manual Sensor Target Range rule and the
Room-XOR-Enclosure-set invariant, not a new validation mechanism.

**Consequences**: adding a genuinely new metric later (e.g. ORP) is a schema migration plus a
`schemas/enclosure_types.py` edit, not just a data row — an accepted trade-off, simplicity and
queryability over runtime flexibility nothing has asked for yet. Bioactive stays orthogonal to
Enclosure Type (see `CONTEXT.md`), gating Plant/Plant Health tracking independently of which of the
four base types applies.
