"""
Redesign preview (requirement 5.4): the user's own photo with the chosen materials applied.

Only the regions that have a material change. Each texture is drawn at real-world scale, then
multiplied by the photo's own shading (light, shadows, weathering) so it sits in the scene.
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
    luminance = np.asarray(photo.convert("L").filter(ImageFilter.GaussianBlur(2)), dtype=np.float32) / 255.0
    result = original.copy()

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

        # Keep the photo's lighting: relative brightness inside the region scales the texture.
        light = luminance[y0:y1, x0:x1]
        shade = np.clip(light / max(float(light[inside].mean()), 1e-3), *SHADE_RANGE) ** 0.85
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
