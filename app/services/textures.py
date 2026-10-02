"""
Procedural material textures at real-world scale (requirement 5.4).

Every texture is generated in code — no image downloads, no licensing questions — and drawn at
its physical size using the photo's scale (pixels per metre): a 600 × 300 mm slab is 600 × 300 mm
on the wall. Outputs are float RGB arrays in [0, 1] of the requested size; railings also return an
alpha channel because they are drawn *over* what is behind them.
"""
import numpy as np
from PIL import Image

from app.catalog import BY_ID as CATALOG_BY_ID


def hex_rgb(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def smooth_noise(height: int, width: int, cell_px: float, rng: np.random.Generator) -> np.ndarray:
    """Value noise in [-1, 1] with features about `cell_px` pixels wide."""
    gh, gw = max(2, int(height / max(cell_px, 1)) + 2), max(2, int(width / max(cell_px, 1)) + 2)
    grid = rng.uniform(-1, 1, (gh, gw)).astype(np.float32)
    image = Image.fromarray(grid, mode="F").resize((width, height), Image.Resampling.BICUBIC)
    return np.clip(np.asarray(image), -1, 1)


def _fill(height: int, width: int, rgb: np.ndarray) -> np.ndarray:
    return np.broadcast_to(rgb, (height, width, 3)).astype(np.float32).copy()


def paint(height, width, ppm, rgb, rng, grain=0.015):
    out = _fill(height, width, rgb)
    out *= 1 + grain * smooth_noise(height, width, max(2, ppm * 0.01), rng)[..., None]
    return out


def textured_paint(height, width, ppm, rgb, rng):
    fine = smooth_noise(height, width, max(1.5, ppm * 0.004), rng)
    coarse = smooth_noise(height, width, max(4, ppm * 0.05), rng)
    return _fill(height, width, rgb) * (1 + 0.09 * fine + 0.04 * coarse)[..., None]


def tiled(height, width, ppm, rgb, rng, *, unit_w_m, unit_h_m, joint_mm, joint_rgb, bond="stack",
          variation=0.08, grain=0.06, grain_m=0.02, speckle=0.0):
    """Tiles, slabs or panels with joints; per-tile colour variation and surface grain."""
    tile_w, tile_h = max(unit_w_m * ppm, 4.0), max(unit_h_m * ppm, 4.0)
    joint = max(joint_mm / 1000 * ppm, 1.0)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    row = np.floor(ys / tile_h)
    offset = (row % 2) * tile_w / 2 if bond == "running" else 0.0
    col = np.floor((xs + offset) / tile_w)
    in_x = (xs + offset) - col * tile_w
    in_y = ys - row * tile_h
    is_joint = (in_x < joint) | (in_y < joint)

    # One brightness / tint offset per tile, looked up by (row, col).
    tile_id = ((row.astype(np.int64) * 7919 + col.astype(np.int64) * 104729) % 9973).astype(np.int64)
    shades = rng.uniform(-variation, variation, 9973).astype(np.float32)
    tints = rng.uniform(-variation / 3, variation / 3, (9973, 3)).astype(np.float32)
    colour = rgb * (1 + shades[tile_id])[..., None] + tints[tile_id]
    colour *= 1 + grain * smooth_noise(height, width, max(1.5, grain_m * ppm), rng)[..., None]
    if speckle:
        dots = rng.uniform(0, 1, (height, width)).astype(np.float32)
        colour *= np.where(dots > 0.93, 1 + speckle, np.where(dots < 0.07, 1 - speckle, 1.0))[..., None]
    colour[is_joint] = joint_rgb
    return colour


def wood_panels(height, width, ppm, rgb, rng, *, board_m=0.15, joint_mm=6):
    """Horizontal wood-look boards with grain streaks."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    board_px = max(board_m * ppm, 4.0)
    board = np.floor(ys / board_px)
    warp = smooth_noise(height, width, max(6, ppm * 0.3), rng) * 6
    grain = np.sin((ys + warp) / max(1.2, ppm * 0.004) + board * 1.7) * 0.5 + 0.5
    shade = rng.uniform(-0.1, 0.1, 4096).astype(np.float32)[(board.astype(np.int64) % 4096)]
    colour = rgb * (0.88 + 0.16 * grain + shade)[..., None]
    joint = (ys - board * board_px) < max(joint_mm / 1000 * ppm, 1.0)
    colour[joint] = rgb * 0.45
    return colour


def railing(height, width, ppm, rgb, rng, *, kind):
    """Bars (MS/SS) or glass panels over whatever is behind; returns (rgb, alpha)."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    colour = _fill(height, width, rgb)
    alpha = np.zeros((height, width), dtype=np.float32)
    rail = max(0.05 * ppm, 2.0)
    top = ys < rail
    bottom = ys > height - max(0.03 * ppm, 1.0)
    if kind == "glass":
        alpha[:] = 0.38
        sheen = np.clip(1 - np.abs((xs - ys * 0.6) % max(width, 1) / max(width, 1) - 0.3) * 4, 0, 1)
        colour = colour * (1 + 0.25 * sheen[..., None])
        post_every = max(1.2 * ppm, 8.0)
        posts = (xs % post_every) < max(0.012 * ppm, 1.0)
        steel = hex_rgb("#c0c4c8")
        colour[top | posts] = steel
        alpha[top | posts] = 1.0
    else:
        spacing = max((0.10 if kind == "ms" else 0.12) * ppm, 3.0)
        bar = max(0.018 * ppm, 1.0)
        bars = (xs % spacing) < bar
        mask = bars | top | bottom
        if kind == "ss":
            colour = colour * (0.85 + 0.3 * (np.sin(xs / max(bar, 1) * np.pi) * 0.5 + 0.5))[..., None]
        alpha[mask] = 1.0
    return np.clip(colour, 0, 1), alpha


GROUT_LIGHT = hex_rgb("#cfcac2")
GROUT_DARK = hex_rgb("#5c554e")


def material_texture(material: dict, color: str | None, height: int, width: int, ppm: float, seed: int):
    """Texture for one material over a height × width pixel area. Returns (rgb, alpha or None)."""
    rng = np.random.default_rng(seed)
    rgb = hex_rgb(color or material.get("swatch") or "#cccccc")
    # Rows from Supabase have no `key`; ids are fixed, so look it up in the catalog.
    key = material.get("key") or CATALOG_BY_ID.get(str(material.get("id")), {}).get("key", "")
    category = material["category"]
    size = material.get("unit_size") or {}

    if category == "railing":
        kind = "glass" if "glass" in key else "ss" if "ss" in key else "ms"
        return railing(height, width, ppm, rgb, rng, kind=kind)
    if category == "texture":
        return textured_paint(height, width, ppm, rgb, rng), None
    if category in ("paint", "plaster"):
        return paint(height, width, ppm, rgb, rng, grain=0.05 if category == "plaster" else 0.015), None
    if key == "panel-hpl":
        return wood_panels(height, width, ppm, rgb, rng), None
    if key == "panel-acp":
        return tiled(height, width, ppm, rgb, rng, unit_w_m=size.get("panel_w_m", 1.22),
                     unit_h_m=size.get("panel_h_m", 2.44), joint_mm=10, joint_rgb=rgb * 0.35,
                     variation=0.02, grain=0.02, grain_m=0.4), None
    if key == "stone-granite":
        return tiled(height, width, ppm, rgb, rng, unit_w_m=size.get("tile_w_m", 0.6),
                     unit_h_m=size.get("tile_h_m", 0.6), joint_mm=4, joint_rgb=GROUT_DARK,
                     variation=0.06, grain=0.05, grain_m=0.01, speckle=0.35), None
    if key == "stone-sandstone":
        return tiled(height, width, ppm, rgb, rng, unit_w_m=size.get("tile_w_m", 0.6),
                     unit_h_m=size.get("tile_h_m", 0.3), joint_mm=7, joint_rgb=rgb * 0.62, bond="running",
                     variation=0.14, grain=0.1, grain_m=0.03), None
    if key == "tile-ceramic-elevation":
        return tiled(height, width, ppm, rgb, rng, unit_w_m=size.get("tile_w_m", 0.45),
                     unit_h_m=size.get("tile_h_m", 0.3), joint_mm=8, joint_rgb=GROUT_LIGHT, bond="running",
                     variation=0.12, grain=0.05, grain_m=0.02), None
    if category == "tiles":
        return tiled(height, width, ppm, rgb, rng, unit_w_m=size.get("tile_w_m", 0.6),
                     unit_h_m=size.get("tile_h_m", 0.3), joint_mm=3, joint_rgb=GROUT_LIGHT,
                     variation=0.04, grain=0.05, grain_m=0.08), None
    if size.get("tile_w_m"):
        return tiled(height, width, ppm, rgb, rng, unit_w_m=size["tile_w_m"], unit_h_m=size["tile_h_m"],
                     joint_mm=5, joint_rgb=GROUT_LIGHT), None
    return paint(height, width, ppm, rgb, rng), None
