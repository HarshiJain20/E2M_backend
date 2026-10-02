"""
Upload preparation: decode, quality-check, normalise, and thumbnail an exterior photo.

Quality checks implement requirement 5.1: reject extremely low-quality input and tell
the user how to take a usable photo. Thresholds are deliberately lenient; a failed
check means the image cannot support segmentation or measurement at all, while a
warning lets the user continue with reduced accuracy.
"""
import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 80_000_000  # ~80 MP; anything larger is not a phone photo

ANALYSIS_SIDE = 1024

EXIF_IFD = 0x8769
EXIF_TAGS = {
    "make": 0x010F,
    "model": 0x0110,
    "focal_length_mm": 0x920A,
    "focal_length_35mm": 0xA405,
}


class ImageRejected(ValueError):
    """The upload is not a decodable image."""


@dataclass
class QualityCheck:
    id: str
    label: str
    status: str  # pass | warn | fail
    value: float
    message: str
    guidance: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PreparedImage:
    original_jpeg: bytes
    working_jpeg: bytes
    thumbnail_jpeg: bytes
    width: int
    height: int
    meta: dict
    checks: list[QualityCheck] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    @property
    def quality_report(self) -> dict:
        return {
            "usable": self.usable,
            "checks": [check.as_dict() for check in self.checks],
        }


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def _resized(image: Image.Image, max_side: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return copy


def _exif_meta(image: Image.Image) -> dict:
    meta: dict = {}
    try:
        exif = image.getexif()
        sub = exif.get_ifd(EXIF_IFD)
    except Exception:  # corrupt EXIF must never block an upload
        return meta
    for key, tag in EXIF_TAGS.items():
        value = exif.get(tag, sub.get(tag))
        if value is None:
            continue
        if key.startswith("focal"):
            try:
                meta[key] = round(float(value), 2)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
        else:
            meta[key] = str(value).strip("\x00 ")[:64]
    return meta


def _laplacian_variance(gray: np.ndarray) -> float:
    lap = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(lap.var())


def assess_quality(image: Image.Image) -> list[QualityCheck]:
    width, height = image.size
    short_side = min(width, height)
    aspect = max(width, height) / short_side
    gray = np.asarray(_resized(image, ANALYSIS_SIDE).convert("L"), dtype=np.float32)
    sharpness = _laplacian_variance(gray)
    brightness = float(gray.mean())
    contrast = float(gray.std())

    checks: list[QualityCheck] = []

    if short_side < 480:
        checks.append(QualityCheck(
            "resolution", "Resolution", "fail", short_side,
            f"The image is only {width}×{height} px, too small to find walls and windows.",
            "Upload the original photo from your camera, not a screenshot or a copy forwarded through a messaging app.",
        ))
    elif short_side < 900:
        checks.append(QualityCheck(
            "resolution", "Resolution", "warn", short_side,
            f"The image is {width}×{height} px. Small details such as railings may be missed.",
            "For best results use a photo at least 1200 px on its shorter side.",
        ))
    else:
        checks.append(QualityCheck("resolution", "Resolution", "pass", short_side, f"{width}×{height} px"))

    if aspect > 3:
        checks.append(QualityCheck(
            "framing", "Framing", "fail", round(aspect, 2),
            "The image is a very narrow strip, so the facade cannot be measured.",
            "Use a normal photo (not a panorama or tight crop) showing the whole front of the house.",
        ))
    else:
        checks.append(QualityCheck("framing", "Framing", "pass", round(aspect, 2), "Standard photo proportions"))

    if sharpness < 15:
        checks.append(QualityCheck(
            "sharpness", "Sharpness", "fail", round(sharpness, 1),
            "The photo is too blurry to detect edges of walls and openings.",
            "Hold the phone steady, tap to focus on the house, and avoid zooming in digitally.",
        ))
    elif sharpness < 60:
        checks.append(QualityCheck(
            "sharpness", "Sharpness", "warn", round(sharpness, 1),
            "The photo is slightly soft; edges may be less precise.",
            "A sharper photo improves both detection and area estimates.",
        ))
    else:
        checks.append(QualityCheck("sharpness", "Sharpness", "pass", round(sharpness, 1), "Edges are clear"))

    if brightness < 35:
        checks.append(QualityCheck(
            "exposure", "Lighting", "fail", round(brightness, 1),
            "The photo is too dark to see the surfaces.",
            "Take the photo in daylight, ideally with the sun behind you or on an overcast day.",
        ))
    elif brightness > 225:
        checks.append(QualityCheck(
            "exposure", "Lighting", "fail", round(brightness, 1),
            "The photo is washed out by too much light.",
            "Avoid shooting into the sun; stand so the facade is evenly lit.",
        ))
    elif brightness < 60 or brightness > 200:
        checks.append(QualityCheck(
            "exposure", "Lighting", "warn", round(brightness, 1),
            "Lighting is uneven, which can hide surface edges.",
            "Daylight with soft, even light gives the most realistic redesigns.",
        ))
    else:
        checks.append(QualityCheck("exposure", "Lighting", "pass", round(brightness, 1), "Well exposed"))

    if contrast < 12:
        checks.append(QualityCheck(
            "contrast", "Detail", "fail", round(contrast, 1),
            "The image has almost no visible detail (blank, foggy, or covered lens).",
            "Make sure the camera lens is clean and the whole house front is in view.",
        ))
    elif contrast < 25:
        checks.append(QualityCheck(
            "contrast", "Detail", "warn", round(contrast, 1),
            "The image has low contrast; some surfaces may merge together.",
            "Try a photo with clearer light and fewer reflections.",
        ))
    else:
        checks.append(QualityCheck("contrast", "Detail", "pass", round(contrast, 1), "Good surface detail"))

    return checks


def prepare_upload(data: bytes, working_max_side: int, thumbnail_max_side: int) -> PreparedImage:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageRejected("The file could not be read as an image. Upload a JPG, PNG or WebP photo.") from exc

    meta = _exif_meta(image)
    meta["original_width"], meta["original_height"] = image.size

    # Apply camera rotation, then drop all metadata (including GPS) by re-encoding.
    image = ImageOps.exif_transpose(image).convert("RGB")
    working = _resized(image, working_max_side)

    return PreparedImage(
        original_jpeg=_encode_jpeg(image, 92),
        working_jpeg=_encode_jpeg(working, 90),
        thumbnail_jpeg=_encode_jpeg(_resized(image, thumbnail_max_side), 80),
        width=working.width,
        height=working.height,
        meta=meta,
        checks=assess_quality(image),
    )
