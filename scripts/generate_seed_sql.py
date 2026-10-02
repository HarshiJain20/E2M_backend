"""Write supabase/seed_materials.sql from app/catalog.py.

    python -m scripts.generate_seed_sql
"""
import json
from pathlib import Path

from app.catalog import MATERIALS

OUT = Path(__file__).resolve().parents[1] / "supabase" / "seed_materials.sql"
COLUMNS = [
    "id", "sor_code", "rate_source", "name", "category", "description", "unit", "material_rate", "labor_rate",
    "wastage_factor", "coverage", "unit_size", "applies_to", "colorable", "swatch", "suitability",
    "maintenance", "durability", "render_prompt", "is_active",
]
JSON_COLUMNS = {"coverage", "unit_size"}


def literal(column: str, value) -> str:
    if value is None:
        return "null"
    if column in JSON_COLUMNS:
        return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"
    if column == "applies_to":
        return "array[" + ", ".join(f"'{v}'" for v in value) + "]::text[]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(float(value))
    return "'" + str(value).replace("'", "''") + "'"


def render() -> str:
    rows = ",\n".join(
        "  (" + ", ".join(literal(c, m.get(c)) for c in COLUMNS) + ")" for m in MATERIALS
    )
    updates = ",\n  ".join(f"{c} = excluded.{c}" for c in COLUMNS if c != "id")
    return f"""-- ════════════════════════════════════════════════════════════════════════════
-- E2M — material catalog seed. GENERATED from app/catalog.py; do not edit by hand.
--   python -m scripts.generate_seed_sql
-- Safe to re-run: existing materials are updated in place (ids are fixed).
-- Rates are indicative starting values (₹ per m² or running metre); verify before relying on them.
-- ════════════════════════════════════════════════════════════════════════════

insert into public.materials ({", ".join(COLUMNS)}) values
{rows}
on conflict (id) do update set
  {updates};
"""


if __name__ == "__main__":
    OUT.write_text(render())
    print(f"Wrote {len(MATERIALS)} materials to {OUT}")
