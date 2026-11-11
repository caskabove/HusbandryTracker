"""Adds the 7 Species Profile Knowledge Base tables (snake_profile,
lizard_profile, insect_profile, saltwater_fish_profile, freshwater_fish_profile,
saltwater_invert_profile, freshwater_invert_profile — see db/schema.sql, CONTEXT.md: Knowledge
Base, Species Profile; ADR 0054), pre-seeded with reference data, and retires the old hardcoded
SPECIES_PROFILES/SPECIES_PROFILE_GROUPS literal from web/static/app.js.

No backfill needed on `animal`: snake_profile/lizard_profile reuse the exact same profile_key
values the old SPECIES_PROFILES literal used, so any Animal row already carrying a
species_profile value (e.g. "ball_python") keeps resolving to the same row.

Ported verbatim from tools/migrate_2026_11_02_species_profile_kb.py (RHA-101; see db/migrate.py, ADR 0059).

The seed rows live here (SEED_SQL), not in schema.sql: schema.sql replays on every startup, so a
built-in species the user deleted would come straight back (RHA-113). This migration seeds an
existing database once; db/migrate.py runs seed() on a brand-new database (see
db/migrations/__init__.py's SEEDS), same pattern as m0028_gene_catalog.
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH


SEED_SQL = """-- Seed data: Snakes/Lizards migrated unchanged from the retired SPECIES_PROFILES literal (ADR
-- 0054) — same keys, same numbers, same order. Feeding intervals were already collapsed to a
-- rounded midpoint there (e.g. "every 5-7 days" -> 6); kept that way here rather than re-expanding
-- to a range, since `animal`/`enclosure`.feeding_interval_days is itself a single integer.
INSERT OR IGNORE INTO snake_profile
    (profile_key, common_name, scientific_name, basking_min_f, basking_max_f, cool_min_f, cool_max_f, night_min_f, night_max_f, humidity_min_pct, humidity_max_pct, feeding_baby_interval_days, feeding_adult_interval_days, notes, sort_order)
VALUES
    ('ball_python', 'Ball Python', 'Python regius', 88, 95, 75, 80, 72, 78, 50, 70, 6, 21, 'ReptiFiles, PetMD', 0),
    ('corn_snake', 'Corn Snake', 'Pantherophis guttatus', 85, 90, 72, 78, 65, 70, 40, 60, 6, 16, 'ReptiFiles, Phoenix Herp', 1),
    ('california_kingsnake', 'California Kingsnake', 'Lampropeltis californiae', 85, 90, 70, 80, 65, 70, 40, 60, 6, 11, 'Phoenix Herp, Josh''s Frogs', 2),
    ('western_hognose', 'Western Hognose Snake', 'Heterodon nasicus', 90, 95, 70, 75, 60, 75, 30, 50, 6, 12, 'ReptiFiles, Bio Dude', 3),
    ('boa_constrictor', 'Boa Constrictor', 'Boa constrictor, Boa imperator', 88, 95, 75, 80, 72, 78, 60, 70, 9, 21, 'ReptiFiles, Dubia', 4),
    ('honduran_milk_snake', 'Honduran Milk Snake', 'Lampropeltis hondurensis', 85, 88, 72, 78, 65, 75, 40, 60, 6, 11, 'Bio Dude, FurryCritter', 5),
    ('rosy_boa', 'Rosy Boa', 'Lichanura trivirgata', 90, 95, 75, 85, 65, 70, 30, 50, 9, 16, 'ReptiFiles, That Pet Place', 6),
    ('kenyan_sand_boa', 'Kenyan Sand Boa', 'Eryx colubrinus', 90, 95, 75, 80, 70, 75, 30, 50, 6, 21, 'ReptiFiles, Bio Dude', 7),
    ('gopher_snake', 'Gopher Snake / Bullsnake', 'Pituophis catenifer', 85, 90, 75, 80, 65, 70, 30, 50, 6, 11, 'Dubia, Reptiles Magazine', 8),
    ('carpet_python', 'Carpet Python', 'Morelia spilota', 88, 95, 75, 80, 70, 75, 50, 60, 9, 18, 'Dubia, Shadows Reptiles', 9),
    ('snake_other', 'Snake (other/unlisted)', NULL, 85, 95, 70, 80, 65, 75, 30, 70, 7, 14, 'Consensus range across the listed snakes above — deliberately wide, pick a named species if possible.', 10);

INSERT OR IGNORE INTO lizard_profile
    (profile_key, common_name, scientific_name, basking_min_f, basking_max_f, cool_min_f, cool_max_f, night_min_f, night_max_f, humidity_min_pct, humidity_max_pct, feeding_baby_interval_days, feeding_adult_interval_days, notes, sort_order)
VALUES
    ('bearded_dragon', 'Bearded Dragon', 'Pogona vitticeps', 105, 115, 70, 85, 60, 72, 30, 40, 1, 1, 'ReptiFiles, PetSmart', 0),
    ('leopard_gecko', 'Leopard Gecko', 'Eublepharis macularius', 90, 95, 70, 80, 60, 75, 30, 40, 1, 3, 'Bio Dude, PetSmart', 1),
    ('crested_gecko', 'Crested Gecko', 'Correlophus ciliatus', 78, 82, 70, 75, 65, 72, 60, 80, 1, 2, 'Zen Habitats, Fluker''s', 2),
    ('blue_tongue_skink', 'Blue-Tongued Skink', 'Tiliqua scincoides intermedia', 105, 115, 70, 80, 65, 75, 40, 60, 1, 2, 'ReptiFiles, Bio Dude', 3),
    ('african_fat_tailed_gecko', 'African Fat-Tailed Gecko', 'Hemitheconyx caudicinctus', 88, 92, 70, 80, 70, 75, 50, 70, 1, 2, 'Dubia, WebMD', 4),
    ('veiled_chameleon', 'Veiled Chameleon', 'Chamaeleo calyptratus', 85, 90, 72, 78, 55, 65, 30, 50, 1, 2, 'ReptiFiles, Dubia', 5),
    ('gargoyle_gecko', 'Gargoyle Gecko', 'Rhacodactylus auriculatus', 82, 85, 70, 75, 65, 72, 50, 70, 1, 2, 'Bio Dude, Josh''s Frogs', 6),
    ('tegu', 'Argentine Black and White Tegu', 'Salvator merianae', 120, 135, 75, 85, 70, 75, 60, 80, 1, 3, 'ReptiFiles, LafeberVet', 7),
    ('green_iguana', 'Green Iguana', 'Iguana iguana', 115, 125, 75, 85, 73, 80, 60, 80, 1, 1, 'ReptiFiles, Chewy', 8),
    ('uromastyx', 'Uromastyx', 'Uromastyx spp.', 120, 130, 80, 85, 70, 80, 10, 35, 1, 1, 'ReptiFiles, That Pet Place', 9),
    ('lizard_other', 'Lizard (other/unlisted)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Deliberately left blank — the ten listed lizards alone span a 78-135°F basking range, so a single averaged number would be unsafe. Pick a named species if at all possible.', 10);

-- Seed data: Insects, and the 4 aquatic categories, researched fresh for this Knowledge Base (ADR
-- 0054) — hobbyist care-sheet consensus ranges, same rigor as the original Snakes/Lizards research
-- but without a per-row citation trail (no specific source was pinned per figure the way the
-- original markdown doc did) — treat as a documented starting point to verify/adjust, same caveat
-- the original doc's own "Ranges are consensus, not law" note already carries.
INSERT OR IGNORE INTO insect_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, humidity_min_pct, humidity_max_pct, lifespan, diet, notes, sort_order)
VALUES
    ('chinese_mantis', 'Chinese Mantis', 'Tenodera sinensis', 70, 85, 50, 70, '~1 year, egg to adult death', 'Live insects (flies, crickets) — daily as a nymph, 2-3x/week as an adult', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('orchid_mantis', 'Orchid Mantis', 'Hymenopus coronatus', 75, 85, 70, 80, '~6-8 months', 'Live flying insects several times a week', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('ghost_mantis', 'Ghost Mantis', 'Phyllocrania paradoxa', 72, 82, 60, 75, '~8-10 months', 'Small live flying insects, 2-3x/week as an adult', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('deaths_head_cockroach', 'Death''s Head Cockroach', 'Blaberus craniifer', 75, 85, 50, 70, '1-2 years as an adult', 'Fruit, vegetables, and protein (fish flakes or dry dog food)', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('madagascar_hissing_cockroach', 'Madagascar Hissing Cockroach', 'Gromphadorhina portentosa', 75, 85, 60, 80, '2-5 years', 'Fruit, vegetables, and protein (fish flakes or dry dog food)', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('hercules_beetle', 'Hercules Beetle', 'Dynastes hercules', 72, 82, 70, 80, '~1 year as an adult (longer as larva)', 'Larva: rotting wood/substrate. Adult: soft fruit.', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('indian_stick_insect', 'Indian Stick Insect', 'Carausius morosus', 68, 80, 50, 70, '~1 year', 'Bramble, ivy, or privet leaves daily', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('macleays_spectre', 'Macleay''s Spectre (Giant Stick Insect)', 'Extatosoma tiaratum', 72, 82, 60, 80, '~18 months', 'Eucalyptus or bramble leaves daily', 'Care-sheet consensus (hobbyist reference ranges).', 7),
    ('insect', 'Insect (other/unlisted)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Deliberately left blank — "Insect" spans far too much (mantids, beetles, roaches, stick insects) for one averaged range. Pick a named species if at all possible.', 8);

INSERT OR IGNORE INTO saltwater_fish_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, salinity_sg_min, salinity_sg_max, ph_min, ph_max, ammonia_ppm_max, nitrite_ppm_max, nitrate_ppm_max, diet, notes, sort_order)
VALUES
    ('clownfish', 'Ocellaris Clownfish', 'Amphiprion ocellaris', 74, 82, 1.020, 1.025, 8.1, 8.4, 0, 0, 10, 'Omnivore — flake/frozen mysis, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('banggai_cardinalfish', 'Banggai Cardinalfish', 'Pterapogon kauderni', 75, 82, 1.020, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — mysis/flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('royal_gramma', 'Royal Gramma', 'Gramma loreto', 72, 78, 1.020, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — mysis/flake, 1x/day', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('firefish_goby', 'Firefish Goby', 'Nemateleotris magnifica', 72, 78, 1.020, 1.024, 8.1, 8.4, 0, 0, 10, 'Carnivore — small meaty foods, 2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('blue_green_chromis', 'Blue-Green Chromis', 'Chromis viridis', 72, 78, 1.020, 1.025, 8.1, 8.4, 0, 0, 15, 'Omnivore — flake/frozen, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('yellow_tang', 'Yellow Tang', 'Zebrasoma flavescens', 72, 78, 1.023, 1.025, 8.1, 8.4, 0, 0, 10, 'Herbivore — nori/algae sheet, daily', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('six_line_wrasse', 'Six-Line Wrasse', 'Pseudocheilinus hexataenia', 72, 78, 1.021, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — varied small meaty foods, daily', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('mandarinfish', 'Mandarinfish', 'Synchiropus splendidus', 72, 78, 1.021, 1.025, 8.1, 8.4, 0, 0, 10, 'Carnivore — live pods/frozen mysis, several small feedings/day; needs an established tank', 'Care-sheet consensus (hobbyist reference ranges).', 7);

INSERT OR IGNORE INTO freshwater_fish_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, ph_min, ph_max, gh_min, gh_max, kh_min, kh_max, ammonia_ppm_max, nitrite_ppm_max, nitrate_ppm_max, diet, notes, sort_order)
VALUES
    ('neon_tetra', 'Neon Tetra', 'Paracheirodon innesi', 72, 78, 6.0, 7.0, 2, 10, 2, 5, 0, 0, 20, 'Omnivore — flake/micro pellets, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('betta', 'Betta', 'Betta splendens', 76, 82, 6.5, 7.5, 5, 15, 3, 8, 0, 0, 20, 'Carnivore — pellets, 1x/day', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('guppy', 'Guppy', 'Poecilia reticulata', 72, 82, 7.0, 8.0, 8, 20, 4, 10, 0, 0, 20, 'Omnivore — flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('platy', 'Platy', 'Xiphophorus maculatus', 70, 78, 7.0, 8.2, 10, 28, 5, 15, 0, 0, 20, 'Omnivore — flake/veg, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('zebra_danio', 'Zebra Danio', 'Danio rerio', 64, 75, 6.5, 7.5, 5, 12, 4, 8, 0, 0, 20, 'Omnivore — flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('cherry_barb', 'Cherry Barb', 'Puntius titteya', 73, 79, 6.0, 7.5, 2, 12, 1, 5, 0, 0, 20, 'Omnivore — flake, 1-2x/day', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('corydoras_catfish', 'Corydoras Catfish', 'Corydoras spp.', 72, 78, 6.5, 7.5, 2, 12, 2, 5, 0, 0, 20, 'Omnivore, bottom feeder — sinking pellets, daily', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('angelfish', 'Angelfish', 'Pterophyllum scalare', 76, 84, 6.5, 7.5, 3, 8, 2, 5, 0, 0, 20, 'Omnivore — flake/pellets, 1x/day', 'Care-sheet consensus (hobbyist reference ranges).', 7);

INSERT OR IGNORE INTO saltwater_invert_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, salinity_sg_min, salinity_sg_max, ph_min, ph_max, alkalinity_dkh_min, alkalinity_dkh_max, calcium_ppm_min, calcium_ppm_max, diet, notes, sort_order)
VALUES
    ('cleaner_shrimp', 'Skunk Cleaner Shrimp', 'Lysmata amboinensis', 74, 82, 1.020, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Scavenger/omnivore — meaty foods and tank leftovers', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('peppermint_shrimp', 'Peppermint Shrimp', 'Lysmata wurdemanni', 74, 82, 1.020, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Omnivore — meaty foods; also eats Aiptasia anemones', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('blue_leg_hermit_crab', 'Blue Leg Hermit Crab', 'Clibanarius tricolor', 74, 82, 1.020, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Omnivore scavenger — algae and tank leftovers', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('emerald_crab', 'Emerald Crab', 'Mithraculus sculptus', 74, 82, 1.022, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Herbivore — algae grazer', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('turbo_snail', 'Turbo Snail', 'Turbo spp.', 74, 82, 1.022, 1.026, 8.1, 8.4, 8, 12, 380, 450, 'Herbivore — algae grazer', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('feather_duster_worm', 'Feather Duster Worm', 'Bispira spp.', 74, 82, 1.022, 1.025, 8.1, 8.4, 8, 12, 380, 450, 'Filter feeder — phytoplankton', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('green_star_polyp', 'Green Star Polyp', 'Pachyclavularia violacea', 75, 82, 1.023, 1.025, 8.1, 8.4, 8, 11, 400, 450, 'Photosynthetic (coral) — occasional target feeding helps but isn''t required', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('condylactis_anemone', 'Condylactis Anemone', 'Condylactis gigantea', 75, 82, 1.023, 1.025, 8.1, 8.4, 8, 12, 400, 450, 'Carnivore — meaty foods, 2-3x/week', 'Care-sheet consensus (hobbyist reference ranges).', 7);

INSERT OR IGNORE INTO freshwater_invert_profile
    (profile_key, common_name, scientific_name, temp_min_f, temp_max_f, ph_min, ph_max, gh_min, gh_max, kh_min, kh_max, diet, sensitivity_notes, notes, sort_order)
VALUES
    ('cherry_shrimp', 'Cherry Shrimp', 'Neocaridina davidi', 65, 78, 6.5, 8.0, 6, 10, 2, 6, 'Omnivore — algae and biofilm grazer', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 0),
    ('crystal_red_shrimp', 'Crystal Red Shrimp', 'Caridina cf. cantonensis', 65, 73, 6.0, 6.8, 4, 6, 0, 2, 'Omnivore — biofilm and specialized shrimp food', 'Copper-sensitive; needs very stable water parameters.', 'Care-sheet consensus (hobbyist reference ranges).', 1),
    ('amano_shrimp', 'Amano Shrimp', 'Caridina multidentata', 64, 78, 6.5, 7.5, 6, 8, 2, 6, 'Algae grazer', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 2),
    ('nerite_snail', 'Nerite Snail', 'Neritina natalensis', 72, 78, 7.0, 8.0, 8, 15, 4, 10, 'Algae grazer', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 3),
    ('mystery_snail', 'Mystery Snail', 'Pomacea bridgesii', 68, 82, 7.0, 8.0, 8, 18, 4, 10, 'Omnivore — algae and vegetables', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 4),
    ('malaysian_trumpet_snail', 'Malaysian Trumpet Snail', 'Melanoides tuberculata', 70, 80, 7.0, 8.0, 6, 15, 3, 8, 'Detritivore — substrate scavenger', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 5),
    ('dwarf_crayfish', 'Dwarf Crayfish (CPO)', 'Cambarellus patzcuarensis', 68, 78, 6.5, 8.0, 6, 15, 3, 8, 'Omnivore scavenger', 'Copper-sensitive; semi-aggressive toward small tankmates.', 'Care-sheet consensus (hobbyist reference ranges).', 6),
    ('assassin_snail', 'Assassin Snail', 'Clea helena', 70, 78, 7.0, 8.0, 8, 15, 3, 8, 'Carnivore — eats pest snails', 'Copper-sensitive — avoid copper-based medications.', 'Care-sheet consensus (hobbyist reference ranges).', 7);
"""


def seed(conn: sqlite3.Connection) -> None:
    """Insert every built-in Knowledge Base species that isn't already there (INSERT OR IGNORE)."""
    conn.executescript(SEED_SQL)


def migrate(conn: sqlite3.Connection) -> None:
    # CREATE TABLE IF NOT EXISTS for the 7 new tables, then the one-time seed. Both no-ops on a re-run.
    conn.executescript(SCHEMA_PATH.read_text())
    seed(conn)
    print("  [done] snake_profile, lizard_profile, insect_profile, saltwater_fish_profile, "
          "freshwater_fish_profile, saltwater_invert_profile, freshwater_invert_profile")
