"""
Material catalog (requirement 5.3) — the single source of truth.

`supabase/seed_materials.sql` is generated from this list (`python -m scripts.generate_seed_sql`)
and the in-memory repository reads it directly, so both always carry the same materials.

Rates are **indicative starting values** in ₹, split into material and labour, per unit
(m² or running metre). The three "CPWD DSR-based" items match the DSR 2021 totals quoted in the
research documents (13.46.1 acrylic paint ₹160.60, 13.45.1 textured paint ₹223.60, 13.1 12 mm
plaster ₹294.85 per m²); the material/labour split is an estimate. All other items are
indicative market rates. Verify against the current DSR / local quotes before relying on them —
users can also edit rates per project (requirement 5.7).
"""
import uuid

# Fixed namespace so every material keeps the same id across seeds and environments.
NAMESPACE = uuid.UUID("6f1c2a52-3c1e-4f0e-9b7a-0e2000000000")

SURFACES = ["wall", "parapet", "pillar", "balcony"]
DSR = "CPWD DSR-based (indicative)"
MARKET = "Indicative market rate"


def _material(key: str, **fields) -> dict:
    return {"id": str(uuid.uuid5(NAMESPACE, key)), "key": key, "is_active": True, **fields}


MATERIALS: list[dict] = [
    # ── Paint & texture ──
    _material(
        "paint-acrylic-exterior",
        name="Acrylic exterior emulsion paint",
        category="paint", sor_code="13.46.1", rate_source=DSR, unit="sqm",
        material_rate=95.0, labor_rate=65.0, wastage_factor=0.05,
        coverage={"litres_per_sqm": 0.167, "coats": 2, "pack_litres": 20, "primer": True},
        applies_to=SURFACES, colorable=True, swatch="#f2e8d5",
        description="Smooth acrylic exterior paint, two coats over one coat of exterior primer.",
        suitability="Most plastered walls; the standard choice for a fresh, even finish.",
        maintenance="Wash with water every 1–2 years; repaint every 5–7 years.",
        durability="Good resistance to rain and fading in moderate climates.",
        render_prompt="smooth matte exterior emulsion paint",
    ),
    _material(
        "paint-weatherproof-premium",
        name="Premium weatherproof emulsion (silicone/elastomeric)",
        category="paint", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=140.0, labor_rate=80.0, wastage_factor=0.05,
        coverage={"litres_per_sqm": 0.143, "coats": 2, "pack_litres": 20, "primer": True},
        applies_to=SURFACES, colorable=True, swatch="#e9e4da",
        description="High-performance exterior paint with silicone additives that repels water and resists hairline cracks.",
        suitability="Walls facing heavy rain or coastal humidity; homes with recurring damp patches.",
        maintenance="Dirt-resistant; wash every 2–3 years; repaint every 8–10 years.",
        durability="Excellent water and UV resistance; bridges hairline cracks.",
        render_prompt="premium weatherproof exterior paint, slight sheen",
    ),
    _material(
        "paint-texture",
        name="Textured exterior paint",
        category="texture", sor_code="13.45.1", rate_source=DSR, unit="sqm",
        material_rate=150.0, labor_rate=75.0, wastage_factor=0.05,
        coverage={"litres_per_sqm": 0.328, "coats": 2, "pack_litres": 25, "primer": True},
        applies_to=SURFACES, colorable=True, swatch="#d9c7a8",
        description="Thick textured coating (sand/roller finish) over exterior primer.",
        suitability="Feature walls and pillars; hides minor plaster unevenness.",
        maintenance="Textures hold dust; wash yearly; recoat every 7–10 years.",
        durability="Very durable and crack-hiding; harder to touch up invisibly.",
        render_prompt="sand-textured exterior wall coating",
    ),
    _material(
        "paint-cement-economy",
        name="Waterproof cement paint (economy)",
        category="paint", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=30.0, labor_rate=25.0, wastage_factor=0.05,
        coverage={"kg_per_sqm": 0.33, "coats": 2, "pack_kg": 25},
        applies_to=SURFACES, colorable=True, swatch="#ece6dc",
        description="Cement-based powder paint mixed with water, two coats.",
        suitability="Budget refresh of compound walls, parapets and service areas.",
        maintenance="Chalks and fades faster; repaint every 3–4 years.",
        durability="Basic weather protection; colours are limited and fade sooner.",
        render_prompt="flat cement paint finish",
    ),
    _material(
        "plaster-cement-12mm",
        name="Cement plaster 12 mm (1:4) — replastering",
        category="plaster", sor_code="13.1", rate_source=DSR, unit="sqm",
        material_rate=160.0, labor_rate=135.0, wastage_factor=0.05,
        coverage={"thickness_mm": 12, "mix": "1:4"},
        applies_to=SURFACES, colorable=False, swatch="#c9c3b8",
        description="New 12 mm cement-sand plaster where the old plaster is cracked or hollow.",
        suitability="Damaged or uneven walls before painting or texturing.",
        maintenance="Must be painted or coated; cure for 7 days before painting.",
        durability="Long-lasting base layer when properly cured.",
        render_prompt="fresh grey cement plaster",
    ),
    # ── Cladding ──
    _material(
        "stone-sandstone",
        name="Sandstone cladding (20–25 mm)",
        category="stone_cladding", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=1300.0, labor_rate=450.0, wastage_factor=0.10,
        unit_size={"tile_w_m": 0.6, "tile_h_m": 0.3},
        applies_to=SURFACES, colorable=False, swatch="#c8a97e",
        description="Natural sandstone slabs fixed with adhesive and anchors, with grouted joints.",
        suitability="Feature walls, entrance pillars and boundary walls for a warm natural look.",
        maintenance="Seal every 2–3 years to limit staining and moss.",
        durability="Very durable; porous, so sealing matters in rainy areas.",
        render_prompt="natural sandstone cladding, stacked rectangular slabs",
    ),
    _material(
        "stone-granite",
        name="Granite cladding (20 mm)",
        category="stone_cladding", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=2400.0, labor_rate=600.0, wastage_factor=0.10,
        unit_size={"tile_w_m": 0.6, "tile_h_m": 0.6},
        applies_to=SURFACES, colorable=False, swatch="#5f5b57",
        description="Polished or flamed granite slabs with mechanical fixing and grooved joints.",
        suitability="Ground-floor walls, pillars and entrances that take knocks and splashes.",
        maintenance="Almost none; occasional washing.",
        durability="Excellent; resists water, stains and abrasion for decades.",
        render_prompt="dark granite stone cladding panels",
    ),
    _material(
        "tile-ceramic-elevation",
        name="Ceramic elevation wall tiles (300 × 450 mm)",
        category="tiles", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=650.0, labor_rate=300.0, wastage_factor=0.08,
        unit_size={"tile_w_m": 0.45, "tile_h_m": 0.3},
        applies_to=SURFACES, colorable=False, swatch="#b9a48f",
        description="Exterior-grade ceramic tiles fixed with polymer tile adhesive.",
        suitability="Budget-friendly patterned or brick-look elevations.",
        maintenance="Wash yearly; check joints and re-grout if water seeps in.",
        durability="Good; individual tiles can loosen on poorly prepared walls.",
        render_prompt="brick-look ceramic elevation tiles",
    ),
    _material(
        "tile-vitrified-elevation",
        name="Vitrified / porcelain elevation tiles (300 × 600 mm)",
        category="tiles", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=950.0, labor_rate=350.0, wastage_factor=0.08,
        unit_size={"tile_w_m": 0.6, "tile_h_m": 0.3},
        applies_to=SURFACES, colorable=False, swatch="#9a8f86",
        description="Low-porosity vitrified tiles in stone or wood looks, fixed with adhesive.",
        suitability="Modern elevations wanting a stone or wood look at lower cost than stone.",
        maintenance="Very low; occasional washing.",
        durability="Excellent stain and water resistance.",
        render_prompt="large-format porcelain stone-look facade tiles",
    ),
    _material(
        "panel-acp",
        name="ACP cladding (4 mm aluminium composite)",
        category="panels", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=1300.0, labor_rate=450.0, wastage_factor=0.10,
        unit_size={"panel_w_m": 1.22, "panel_h_m": 2.44},
        applies_to=SURFACES, colorable=True, swatch="#8c9399",
        description="Aluminium composite panels on an aluminium frame with sealed joints.",
        suitability="Modern, flat, single-colour facades and feature bands.",
        maintenance="Wash every 1–2 years; check joint sealant.",
        durability="Good; choose fire-retardant (FR) grade panels.",
        render_prompt="smooth metallic aluminium composite panels with fine joints",
    ),
    _material(
        "panel-hpl",
        name="HPL exterior panels (wood look, 8 mm)",
        category="panels", sor_code=None, rate_source=MARKET, unit="sqm",
        material_rate=2800.0, labor_rate=600.0, wastage_factor=0.10,
        unit_size={"panel_w_m": 1.3, "panel_h_m": 3.05},
        applies_to=SURFACES, colorable=False, swatch="#8a5a3b",
        description="High-pressure laminate panels with a wood finish on a ventilated frame.",
        suitability="Warm wood-look features without the upkeep of real timber.",
        maintenance="Very low; wash yearly.",
        durability="UV- and weather-resistant for 10+ years.",
        render_prompt="wood-grain exterior laminate cladding boards",
    ),
    # ── Railings ──
    _material(
        "railing-ms",
        name="MS railing, painted (900 mm high)",
        category="railing", sor_code=None, rate_source=MARKET, unit="rmt",
        material_rate=1600.0, labor_rate=500.0, wastage_factor=0.05,
        applies_to=["railing"], colorable=True, swatch="#2b2b2b",
        description="Mild-steel railing with primer and two coats of enamel paint.",
        suitability="Balconies and terraces on a budget; any colour.",
        maintenance="Repaint every 2–3 years to prevent rust.",
        durability="Strong; rusts if the paint is not maintained.",
        render_prompt="black painted mild steel balcony railing",
    ),
    _material(
        "railing-ss",
        name="Stainless steel railing (SS 304, 900 mm high)",
        category="railing", sor_code=None, rate_source=MARKET, unit="rmt",
        material_rate=3200.0, labor_rate=700.0, wastage_factor=0.05,
        applies_to=["railing"], colorable=False, swatch="#c0c4c8",
        description="Grade 304 stainless steel posts and rails with a brushed finish.",
        suitability="Modern balconies and stairs; low upkeep.",
        maintenance="Wipe occasionally; no painting.",
        durability="Excellent corrosion resistance (use SS 316 near the sea).",
        render_prompt="brushed stainless steel balcony railing",
    ),
    _material(
        "railing-glass",
        name="Toughened glass railing (12 mm, SS fittings)",
        category="railing", sor_code=None, rate_source=MARKET, unit="rmt",
        material_rate=6500.0, labor_rate=1200.0, wastage_factor=0.05,
        applies_to=["railing"], colorable=False, swatch="#bcd7e0",
        description="12 mm toughened glass panels with stainless steel spigots and handrail.",
        suitability="Open views and a contemporary look on balconies and terraces.",
        maintenance="Clean glass monthly in dusty areas.",
        durability="Very durable; use toughened (or laminated) safety glass only.",
        render_prompt="frameless clear toughened glass balcony railing",
    ),
]

BY_ID = {m["id"]: m for m in MATERIALS}
