"""
Surface area and length estimation (requirement 5.5).

Sizes are computed here, from each region's outline and one scale per photo, every time a
project is read. They therefore update immediately when the user edits regions or adds a
measurement, without re-running the AI service.

Scale (metres per pixel), best source first:
  1. user      — the user measured one region ("door 1 is 2.1 m tall")
  2. reference — standard sizes of detected doors (2.1 m tall), else windows (1.2 m tall)
  3. depth     — the depth model's distance to each region ÷ the camera focal length
  4. assumed   — 10 m camera distance with a typical phone lens (flagged as low accuracy)

A region the user measured exactly (segments.user_dimension) uses that size instead.

All sources assume each surface roughly faces the camera; see the limitations notes.
Walls are reported net of the windows and doors that sit inside them.
"""
import statistics
from dataclasses import dataclass

from app.domain import measure_type

STANDARD_HEIGHTS_M = {"door": 2.1, "window": 1.2}
OPENING_LABELS = ("window", "door")
ASSUMED_DISTANCE_M = 10.0
PHONE_FOCAL_RATIO = 26 / 36  # typical phone main camera: 26 mm equivalent on a 36 mm frame
LABEL_NAMES = {
    "wall": "wall", "window": "window", "door": "door", "balcony": "balcony", "pillar": "pillar",
    "parapet": "parapet wall", "gate": "gate", "roof_edge": "roof edge", "railing": "railing",
}


@dataclass
class Scale:
    source: str  # user | reference | depth | assumed
    detail: str
    metres_per_px: float | None  # None → per-region depth

    def for_segment(self, segment: dict, focal_px: float) -> float:
        if self.metres_per_px is not None:
            return self.metres_per_px
        return (segment.get("depth_stats") or {}).get("median_m", ASSUMED_DISTANCE_M) / focal_px


def user_size(segment: dict, kind: str) -> float | None:
    """The user's exact size for this region, if it matches the region's type."""
    size = segment.get("user_dimension") or {}
    if kind == "length":
        return size.get("length_m")
    if size.get("area_sqm"):
        return size["area_sqm"]
    if size.get("width_m") and size.get("height_m"):
        return size["width_m"] * size["height_m"]
    return None


def pixel_extent(segment: dict, dimension: str, width: int, height: int) -> float:
    x0, y0, x1, y1 = segment["bbox"]
    return (x1 - x0) * width if dimension == "width" else (y1 - y0) * height


def pixel_area(segment: dict, width: int, height: int) -> float:
    points = [(x * width, y * height) for x, y in segment["polygon"]]
    total = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))
    return abs(total) / 2


def pixel_run(segment: dict, width: int, height: int) -> float:
    """Length of a linear element: the long side of its bounding box."""
    return max(pixel_extent(segment, "width", width, height), pixel_extent(segment, "height", width, height))


def point_in_polygon(x: float, y: float, polygon: list) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def focal_length_px(photo: dict) -> float:
    """Focal length from the depth model, else from the photo's EXIF, else a typical phone."""
    measurement = photo.get("measurement") or {}
    long_side = max(photo["image_width"], photo["image_height"])
    if measurement.get("focal_source") == "model" and measurement.get("focal_length_px"):
        return float(measurement["focal_length_px"])
    focal_35mm = (photo.get("image_meta") or {}).get("focal_length_35mm")
    if focal_35mm:
        return float(focal_35mm) / 36 * long_side
    return PHONE_FOCAL_RATIO * long_side


def resolve_scale(photo: dict, segments: list[dict]) -> Scale:
    width, height = photo["image_width"], photo["image_height"]
    measurement = photo.get("measurement") or {}

    reference = measurement.get("reference")
    if reference:
        segment = next((s for s in segments if str(s["id"]) == str(reference["segment_id"])), None)
        if segment and pixel_extent(segment, reference["dimension"], width, height) > 0:
            px = pixel_extent(segment, reference["dimension"], width, height)
            name = LABEL_NAMES.get(segment["label"], segment["label"])
            return Scale("user", f"Your measurement: {name} {reference['dimension']} {reference['metres']:g} m",
                         reference["metres"] / px)

    for label, metres in STANDARD_HEIGHTS_M.items():
        heights = [pixel_extent(s, "height", width, height) for s in segments if s["label"] == label]
        heights = [h for h in heights if h > 0]
        if heights:
            count = f"{len(heights)} {label}{'s' if len(heights) > 1 else ''}"
            return Scale("reference", f"Standard {label} height {metres:g} m ({count} in the photo)",
                         statistics.median(metres / h for h in heights))

    if measurement.get("focal_source") == "model" and any(
        (s.get("depth_stats") or {}).get("median_m") for s in segments
    ):
        return Scale("depth", "Estimated from the depth model's distance to each surface", None)

    return Scale("assumed", f"Assumed {ASSUMED_DISTANCE_M:g} m camera distance — add a measurement for accuracy",
                 ASSUMED_DISTANCE_M / focal_length_px(photo))


def measure_photo(photo: dict, segments: list[dict]) -> tuple[list[dict], Scale]:
    """Segments with computed area_sqm / length_m (walls also net_area_sqm, openings_sqm)."""
    width, height = photo["image_width"], photo["image_height"]
    scale = resolve_scale(photo, segments)
    focal = focal_length_px(photo)

    measured = []
    for segment in segments:
        metres_per_px = scale.for_segment(segment, focal)
        kind = measure_type(segment["label"])
        row = {**segment, "measure_type": kind, "area_sqm": None, "length_m": None, "scale_source": scale.source,
               "size_source": "estimated", "user_size": segment.get("user_dimension")}
        exact = user_size(segment, kind)
        if kind == "length":
            value = exact if exact is not None else pixel_run(segment, width, height) * metres_per_px
            row["length_m"] = round(value, 2)
        else:
            value = exact if exact is not None else pixel_area(segment, width, height) * metres_per_px**2
            row["area_sqm"] = round(value, 2)
        if exact is not None:
            row["size_source"] = "user"
        measured.append(row)

    # Deduct each window/door from the (largest) wall that contains its centre.
    walls = sorted((s for s in measured if s["label"] == "wall"), key=lambda s: s["area_sqm"], reverse=True)
    for wall in walls:
        wall["openings_sqm"] = 0.0
    for opening in (s for s in measured if s["label"] in OPENING_LABELS):
        x0, y0, x1, y1 = opening["bbox"]
        centre = ((x0 + x1) / 2, (y0 + y1) / 2)
        wall = next((w for w in walls if point_in_polygon(*centre, w["polygon"])), None)
        if wall:
            wall["openings_sqm"] += opening["area_sqm"]
    for wall in walls:
        wall["openings_sqm"] = round(wall["openings_sqm"], 2)
        wall["net_area_sqm"] = round(max(wall["area_sqm"] - wall["openings_sqm"], 0.0), 2)
    return measured, scale
