"""Adds the Gene Catalog (`gene` table; see db/schema.sql, CONTEXT.md: Gene, Gene Catalog; RHA-104)
and seeds it with common single-gene morphs for six species.

The seed lives here, not as INSERT OR IGNORE rows in schema.sql (which is how the Knowledge Base
seeds itself), because schema.sql replays on every startup: a seeded Gene the user deleted would
come straight back. A migration runs once. db/migrate.py also calls seed() when it creates a
brand-new database, since a fresh install skips the migrations themselves (see
db/migrations/__init__.py's SEEDS).

Only proven single-gene traits are seeded. Polygenic, line-bred looks (crested gecko Harlequin or
Dalmatian, leopard gecko Tangerine or Hypo, gargoyle gecko Red Stripe or Reticulated) are not
Genes; they belong in Morph. Gargoyle gecko gets no seed rows: none of its traits has a widely
accepted single-gene inheritance, so a seeded list would be guesswork. Allelic groups (ball python
Mojave/Lesser, corn snake Motley/Stripe) are seeded as independent Genes, since alleles aren't
modeled yet (see CONTEXT.md: Gene).

Each entry is (species_category, species_key, name, inheritance, notes). species_key is the
Knowledge Base profile_key, which never changes when a species is renamed.
"""
from __future__ import annotations

import sqlite3

from db.migrations._common import SCHEMA_PATH

R, CD, D = "recessive", "co_dominant", "dominant"

GENES: list[tuple[str, str, str, str, str | None]] = [
    # Ball python (Python regius)
    ("snake", "ball_python", "Albino", R, "Amelanistic: white and yellow with red eyes."),
    ("snake", "ball_python", "Piebald", R, "Patches of pure white; the amount of white varies widely."),
    ("snake", "ball_python", "Clown", R, None),
    ("snake", "ball_python", "Axanthic", R, "Several unrelated lines (e.g. VPI, TSK, Jolliff) that are not compatible with each other."),
    ("snake", "ball_python", "Genetic Stripe", R, None),
    ("snake", "ball_python", "Lavender Albino", R, "Not compatible with Albino; a separate amelanistic mutation."),
    ("snake", "ball_python", "Hypo", R, "Also sold as Ghost."),
    ("snake", "ball_python", "Pastel", CD, "Super form: Super Pastel."),
    ("snake", "ball_python", "Mojave", CD, "Allelic with Lesser and Butter: any two of them make a Blue-Eyed Leucistic (BEL)."),
    ("snake", "ball_python", "Lesser", CD, "Allelic with Mojave and Butter: any two of them make a Blue-Eyed Leucistic (BEL)."),
    ("snake", "ball_python", "Butter", CD, "Allelic with Mojave and Lesser: any two of them make a Blue-Eyed Leucistic (BEL)."),
    ("snake", "ball_python", "Fire", CD, "Super form: Black-Eyed Leucistic."),
    ("snake", "ball_python", "Banana", CD, "Also sold as Coral Glow. Inheritance can look sex-linked in some pairings."),
    ("snake", "ball_python", "Enchi", CD, "Super form: Super Enchi."),
    ("snake", "ball_python", "Yellow Belly", CD, "Super form: Ivory."),
    ("snake", "ball_python", "Cinnamon", CD, "Super form: Super Cinnamon (solid dark brown)."),
    ("snake", "ball_python", "Black Pastel", CD, "Super form: Super Black Pastel (solid dark)."),
    ("snake", "ball_python", "Spotnose", CD, None),
    ("snake", "ball_python", "Spider", D, "Associated with a neurological wobble; no distinct Super form."),
    ("snake", "ball_python", "Pinstripe", D, None),

    # Leopard gecko (Eublepharis macularius)
    ("lizard", "leopard_gecko", "Tremper Albino", R, "The three albino strains are not compatible: Tremper x Bell gives normal-looking hets."),
    ("lizard", "leopard_gecko", "Bell Albino", R, "Not compatible with Tremper or Rainwater albino."),
    ("lizard", "leopard_gecko", "Rainwater Albino", R, "Not compatible with Tremper or Bell albino."),
    ("lizard", "leopard_gecko", "Blizzard", R, "Patternless white to grey."),
    ("lizard", "leopard_gecko", "Murphy Patternless", R, None),
    ("lizard", "leopard_gecko", "Eclipse", R, "Solid black eyes; often adds white on the snout and tail."),
    ("lizard", "leopard_gecko", "Marble Eye", R, None),
    ("lizard", "leopard_gecko", "Mack Snow", CD, "Super form: Super Snow."),
    ("lizard", "leopard_gecko", "GEM Snow", CD, None),
    ("lizard", "leopard_gecko", "TUG Snow", CD, None),
    ("lizard", "leopard_gecko", "Lemon Frost", CD, "Linked to iridophoroma (skin tumors), especially in the Super form."),
    ("lizard", "leopard_gecko", "Giant", CD, "Super form: Super Giant."),
    ("lizard", "leopard_gecko", "Enigma", D, "Linked to Enigma Syndrome (neurological: circling, poor feeding response)."),
    ("lizard", "leopard_gecko", "White & Yellow", D, "Also written W&Y."),

    # Crested gecko (Correlophus ciliatus)
    ("lizard", "crested_gecko", "Lilly White", CD, "The Super form is reported to be non-viable; don't pair two Lilly Whites."),
    ("lizard", "crested_gecko", "Cappuccino", CD, "Super form: Frappuccino. Supers have been linked to shortened snouts and breathing problems."),
    ("lizard", "crested_gecko", "Axanthic", R, None),
    ("lizard", "crested_gecko", "Soft Scale", CD, "Super form: Super Soft Scale."),

    # Bearded dragon (Pogona vitticeps)
    ("lizard", "bearded_dragon", "Hypo", R, "Hypomelanistic: lighter colors and clear nails."),
    ("lizard", "bearded_dragon", "Translucent", R, "See-through scales; often dark eyes."),
    ("lizard", "bearded_dragon", "Leatherback", CD, "Reduced scales. Super form: Silkback, which needs extra skin care."),
    ("lizard", "bearded_dragon", "Witblits", R, "Patternless. Witblits combined with Zero is sold as Wero."),
    ("lizard", "bearded_dragon", "Zero", R, "Patternless, silver to white."),
    ("lizard", "bearded_dragon", "Dunner", D, "Scales point in irregular directions, giving a spotted pattern."),

    # Corn snake (Pantherophis guttatus)
    ("snake", "corn_snake", "Amelanistic", R, "Also called Amel or Red Albino."),
    ("snake", "corn_snake", "Anerythristic", R, "Also called Anery (type A)."),
    ("snake", "corn_snake", "Charcoal", R, "Also called Anery B; not compatible with Anerythristic."),
    ("snake", "corn_snake", "Caramel", R, None),
    ("snake", "corn_snake", "Lavender", R, None),
    ("snake", "corn_snake", "Hypomelanistic", R, "Also called Hypo A."),
    ("snake", "corn_snake", "Motley", R, "Allelic with Stripe."),
    ("snake", "corn_snake", "Stripe", R, "Allelic with Motley."),
    ("snake", "corn_snake", "Diffused", R, "Also called Bloodred."),
    ("snake", "corn_snake", "Sunkissed", R, None),
    ("snake", "corn_snake", "Dilute", R, None),
    ("snake", "corn_snake", "Cinder", R, None),
    ("snake", "corn_snake", "Kastanie", R, None),
    ("snake", "corn_snake", "Palmetto", R, None),
    ("snake", "corn_snake", "Scaleless", R, None),
    ("snake", "corn_snake", "Tessera", D, None),
]


def seed(conn: sqlite3.Connection) -> int:
    """Insert every seed Gene that isn't already there; returns how many were added."""
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO gene (species_category, species_key, name, inheritance, notes) VALUES (?, ?, ?, ?, ?)",
        GENES,
    )
    return conn.total_changes - before


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())  # CREATE TABLE IF NOT EXISTS gene
    added = seed(conn)
    print(f"  [done] gene table; seeded {added} Gene(s)")
