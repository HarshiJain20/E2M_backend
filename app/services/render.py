"""
Redesign preview (requirement 5.4): the user's own photo with the chosen materials applied.

Only the regions that have a material change. Each texture is drawn at real-world scale, then
multiplied by the photo's own lighting so it sits in the scene. Only the *broad* lighting is kept
(shadows, light falloff), averaged over ~half a metre: the old surface's own pattern (tiles,
bricks, grout lines, stains) must not show through the new material.
Windows and doors are put back from the original afterwards, so the structure is unchanged.
"""
import io
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.services.measurement import Scale
from app.services.textures import material_texture

OPENINGS = ("window", "door")
SHADE_RANGE = (0.55, 1.45)
LIGHTING_CELL_M = 0.6  # larger than a tile or brick, smaller than a shadow


def _bbox_px(segment: dict, width: int, height: int, pad: int = 2) -> tuple[int, int, int, int]:
    xs = [x * width for x, _ in segment["polygon"]]
    ys = [y * height for _, y in segment["polygon"]]
    x0, y0 = max(int(min(xs)) - pad, 0), max(int(min(ys)) - pad, 0)
    x1, y1 = min(int(max(xs)) + pad + 1, width), min(int(max(ys)) + pad + 1, height)
    return x0, y0, x1, y1


def _mask(segment: dict, box: tuple[int, int, int, int], width: int, height: int, feather: float) -> np.ndarray:
    x0, y0, x1, y1 = box
    image = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(image).polygon([(x * width - x0, y * height - y0) for x, y in segment["polygon"]], fill=255)
    if feather:
        image = image.filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(image, dtype=np.float32) / 255.0


def _lighting(luminance: np.ndarray, weight: np.ndarray, cell_px: float) -> np.ndarray:
    """Low-frequency brightness: weighted box average on a coarse grid, smoothly upsampled.

    `weight` is 1 on the surface and 0 elsewhere (outside the region, windows, doors), so dark
    glass or the sky next to a wall does not leak into its lighting.
    """
    height, width = luminance.shape
    grid = (max(1, round(width / cell_px)), max(1, round(height / cell_px)))

    def smooth(values: np.ndarray) -> np.ndarray:
        small = Image.fromarray(values.astype(np.float32)).resize(grid, Image.Resampling.BOX)
        return np.asarray(small.resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32)

    total, count = smooth(luminance * weight), smooth(weight)
    fallback = float((luminance * weight).sum() / max(weight.sum(), 1e-6))
    return np.where(count > 0.05, total / np.maximum(count, 1e-6), fallback)


def _seed(segment_id) -> int:
    return zlib.crc32(str(segment_id).encode())


def render_design(
    image_bytes: bytes,
    segments: list[dict],
    assignments: list[dict],
    materials_by_id: dict[str, dict],
    scale: Scale,
    focal_px: float,
) -> bytes:
    """JPEG of the photo with each assigned region re-surfaced in its material."""
    with Image.open(io.BytesIO(image_bytes)) as source:
        photo = ImageOps.exif_transpose(source).convert("RGB")
    width, height = photo.size
    original = np.asarray(photo, dtype=np.float32) / 255.0
    luminance = np.asarray(photo.convert("L"), dtype=np.float32) / 255.0
    result = original.copy()

    # Windows and doors are excluded when reading a wall's lighting.
    openings = Image.new("L", (width, height), 0)
    for segment in segments:
        if segment["label"] in OPENINGS:
            ImageDraw.Draw(openings).polygon([(x * width, y * height) for x, y in segment["polygon"]], fill=255)
    surface = 1.0 - np.asarray(openings, dtype=np.float32) / 255.0

    by_segment = {str(a["segment_id"]): a for a in assignments}
    targets = [s for s in segments if str(s["id"]) in by_segment
               and str(by_segment[str(s["id"])]["material_id"]) in materials_by_id]
    # Large surfaces first, so pillars and railings in front of a wall are drawn over it.
    targets.sort(key=lambda s: (s["bbox"][2] - s["bbox"][0]) * (s["bbox"][3] - s["bbox"][1]), reverse=True)

    for segment in targets:
        assignment = by_segment[str(segment["id"])]
        material = materials_by_id[str(assignment["material_id"])]
        box = _bbox_px(segment, width, height)
        x0, y0, x1, y1 = box
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        mask = _mask(segment, box, width, height, feather=1.0)
        inside = mask > 0.5
        if not inside.any():
            continue

        pixels_per_metre = 1.0 / scale.for_segment(segment, focal_px)
        texture, alpha = material_texture(material, assignment.get("color"), y1 - y0, x1 - x0,
                                          pixels_per_metre, _seed(segment["id"]))

        # Keep the photo's broad lighting (not the old surface's pattern) relative to the region's average.
        weight = inside * surface[y0:y1, x0:x1]
        if weight.sum() < 1:
            weight = inside.astype(np.float32)
        light = _lighting(luminance[y0:y1, x0:x1], weight, LIGHTING_CELL_M * pixels_per_metre)
        average = float((light * weight).sum() / weight.sum())
        shade = np.clip(light / max(average, 1e-3), *SHADE_RANGE) ** 0.85
        coverage = mask if alpha is None else mask * alpha
        region = result[y0:y1, x0:x1]
        result[y0:y1, x0:x1] = region * (1 - coverage[..., None]) + np.clip(texture * shade[..., None], 0, 1) * coverage[..., None]

    # Windows and doors are not re-surfaced: restore them from the original photo.
    for segment in segments:
        if segment["label"] not in OPENINGS:
            continue
        box = _bbox_px(segment, width, height)
        x0, y0, x1, y1 = box
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        mask = _mask(segment, box, width, height, feather=0.8)[..., None]
        result[y0:y1, x0:x1] = result[y0:y1, x0:x1] * (1 - mask) + original[y0:y1, x0:x1] * mask

    buffer = io.BytesIO()
    Image.fromarray((np.clip(result, 0, 1) * 255).round().astype(np.uint8)).save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


def region_mask_png(segments: list[dict], assignments: list[dict], width: int, height: int) -> bytes:
    """White where a material is applied (minus windows and doors), black elsewhere."""
    assigned = {str(a["segment_id"]) for a in assignments}
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for segment in segments:
        if str(segment["id"]) in assigned:
            draw.polygon([(x * width, y * height) for x, y in segment["polygon"]], fill=255)
    for segment in segments:
        if segment["label"] in OPENINGS:
            draw.polygon([(x * width, y * height) for x, y in segment["polygon"]], fill=0)
    buffer = io.BytesIO()
    mask.save(buffer, format="PNG")
    return buffer.getvalue()


PART_NAMES = {"wall": "main walls", "parapet": "parapet wall", "pillar": "pillars", "balcony": "balcony",
              "railing": "balcony railing"}


def photoreal_prompt(segments: list[dict], assignments: list[dict], materials_by_id: dict[str, dict]) -> str:
    """Describe each re-surfaced part in words, e.g. "main walls: natural sandstone cladding"."""
    labels = {str(s["id"]): s["label"] for s in segments}
    parts: dict[str, str] = {}
    for a in assignments:
        label = labels.get(str(a["segment_id"]))
        material = materials_by_id.get(str(a["material_id"]))
        if label and material:
            description = material.get("render_prompt") or material["name"]
            if a.get("color") and material.get("colorable"):
                description += f" in colour {a['color']}"
            parts.setdefault(PART_NAMES.get(label, label), description)
    described = "; ".join(f"{part}: {text}" for part, text in parts.items())
    return (f"Photograph of a residential house exterior after renovation. {described}. "
            "Photorealistic, natural daylight, realistic material texture, sharp detail, same camera angle.")
