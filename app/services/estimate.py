"""
Bill of quantities and cost estimate (requirements 5.6 and 5.7).

Computed live for each design from the measured regions (services.measurement) and the
materials applied to them, so every edit to regions, sizes, materials or rates shows at once.

  quantity       = measured size × (1 + wastage)
  material cost  = quantity × material rate          (you buy the wastage)
  labour cost    = measured size × labour rate       (you don't pay labour on offcuts)

Only the counted (primary) photo of each side of the house is included, so a wall photographed
twice is never priced twice. Rates come from the catalog unless the user changed them for this
project. GST is a separate line that can be switched off.
"""
import math
from collections import defaultdict

PRIMER_LITRES_PER_SQM = 0.09  # one coat of exterior primer (DSR note: 0.90 L per 10 m²)
LABEL_NAMES = {
    "wall": "walls", "window": "windows", "door": "doors", "balcony": "balconies", "pillar": "pillars",
    "parapet": "parapet walls", "gate": "gates", "roof_edge": "roof edges", "railing": "railings",
}


def measured_size(segment: dict) -> float:
    if segment["measure_type"] == "length":
        return segment.get("length_m") or 0.0
    value = segment.get("net_area_sqm")
    return value if value is not None else segment.get("area_sqm") or 0.0


def purchase_quantities(material: dict, quantity: float, measured: float) -> list[dict]:
    """What to buy: litres and cans of paint, bags, tiles, slabs or sheets."""
    coverage = material.get("coverage") or {}
    size = material.get("unit_size") or {}
    items: list[dict] = []
    if coverage.get("litres_per_sqm"):
        litres = quantity * coverage["litres_per_sqm"]
        item = {"item": "Paint", "amount": round(litres, 1), "unit": "litres"}
        if coverage.get("pack_litres"):
            item["packs"] = math.ceil(litres / coverage["pack_litres"])
            item["pack"] = f"{coverage['pack_litres']:g} L can"
        items.append(item)
        if coverage.get("primer"):
            items.append({"item": "Primer", "amount": round(measured * PRIMER_LITRES_PER_SQM, 1), "unit": "litres"})
    elif coverage.get("kg_per_sqm"):
        kg = quantity * coverage["kg_per_sqm"]
        item = {"item": "Cement paint", "amount": round(kg, 1), "unit": "kg"}
        if coverage.get("pack_kg"):
            item["packs"] = math.ceil(kg / coverage["pack_kg"])
            item["pack"] = f"{coverage['pack_kg']:g} kg bag"
        items.append(item)
    if size.get("tile_w_m") and size.get("tile_h_m"):
        name = "Slabs" if material.get("category") == "stone_cladding" else "Tiles"
        count = math.ceil(quantity / (size["tile_w_m"] * size["tile_h_m"]))
        items.append({"item": name, "amount": count, "unit": f"{size['tile_w_m'] * 1000:g} × {size['tile_h_m'] * 1000:g} mm"})
    if size.get("panel_w_m") and size.get("panel_h_m"):
        count = math.ceil(quantity / (size["panel_w_m"] * size["panel_h_m"]))
        items.append({"item": "Sheets", "amount": count, "unit": f"{size['panel_w_m']:g} × {size['panel_h_m']:g} m"})
    return items


def estimate_variant(
    variant: dict,
    photos: list[dict],
    segments: list[dict],
    materials_by_id: dict[str, dict],
    overrides_by_material: dict[str, dict],
    include_gst: bool,
    gst_rate: float,
) -> dict:
    counted_photos = {str(p["id"]) for p in photos if p["is_primary"]}
    segments_by_id = {str(s["id"]): s for s in segments}
    assignable = {label for m in materials_by_id.values() for label in m["applies_to"]}

    groups: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    excluded = 0
    for assignment in variant.get("assignments", []):
        segment = segments_by_id.get(str(assignment["segment_id"]))
        material = materials_by_id.get(str(assignment["material_id"]))
        if segment is None or material is None:
            continue
        if str(segment["photo_id"]) not in counted_photos:
            excluded += 1
            continue
        groups[(str(material["id"]), assignment.get("color"))].append(segment)

    assigned = {str(a["segment_id"]) for a in variant.get("assignments", [])}
    missing = [
        s for s in segments
        if str(s["photo_id"]) in counted_photos and s["label"] in assignable and str(s["id"]) not in assigned
    ]

    lines = []
    for (material_id, color), regions in groups.items():
        material = materials_by_id[material_id]
        override = overrides_by_material.get(material_id) or {}
        material_rate = override.get("material_rate") if override.get("material_rate") is not None else material["material_rate"]
        labor_rate = override.get("labor_rate") if override.get("labor_rate") is not None else material["labor_rate"]
        measured = sum(measured_size(s) for s in regions)
        quantity = measured * (1 + material["wastage_factor"])
        where: dict[str, int] = defaultdict(int)
        for s in regions:
            where[s["label"]] += 1
        material_cost = quantity * material_rate
        labor_cost = measured * labor_rate
        lines.append({
            "material_id": material_id,
            "name": material["name"],
            "category": material["category"],
            "unit": material["unit"],
            "sor_code": material.get("sor_code"),
            "rate_source": material.get("rate_source"),
            "color": color,
            "where": [{"label": label, "count": count, "name": LABEL_NAMES.get(label, label)}
                      for label, count in sorted(where.items())],
            "segment_ids": [str(s["id"]) for s in regions],
            "measured_qty": round(measured, 2),
            "wastage_factor": material["wastage_factor"],
            "quantity": round(quantity, 2),
            "purchase": purchase_quantities(material, quantity, measured),
            "material_rate": material_rate,
            "labor_rate": labor_rate,
            "catalog_material_rate": material["material_rate"],
            "catalog_labor_rate": material["labor_rate"],
            "rate_changed": bool(override),
            "material_cost": round(material_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "total": round(material_cost + labor_cost, 2),
        })
    lines.sort(key=lambda line: (line["category"], line["name"], line["color"] or ""))

    categories: dict[str, dict] = {}
    for line in lines:
        entry = categories.setdefault(line["category"], {"category": line["category"], "material_cost": 0.0,
                                                         "labor_cost": 0.0, "total": 0.0})
        for key in ("material_cost", "labor_cost", "total"):
            entry[key] = round(entry[key] + line[key], 2)

    material_total = round(sum(line["material_cost"] for line in lines), 2)
    labor_total = round(sum(line["labor_cost"] for line in lines), 2)
    subtotal = round(material_total + labor_total, 2)
    gst = round(subtotal * gst_rate, 2) if include_gst else 0.0
    return {
        "variant_id": str(variant["id"]),
        "name": variant["name"],
        "lines": lines,
        "categories": list(categories.values()),
        "material_total": material_total,
        "labor_total": labor_total,
        "subtotal": subtotal,
        "include_gst": include_gst,
        "gst_rate": gst_rate,
        "gst": gst,
        "grand_total": round(subtotal + gst, 2),
        "regions_without_material": len(missing),
        "regions_not_counted": excluded,
    }
