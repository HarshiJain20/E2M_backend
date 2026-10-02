"""Measurement maths, checked against hand calculations on a 1000 × 800 px photo."""
import pytest

from app.services.measurement import focal_length_px, measure_photo, point_in_polygon, resolve_scale


def rect(label, x0, y0, x1, y1, sid=None, depth=None):
    return {
        "id": sid or f"{label}-{x0}-{y0}", "photo_id": "p1", "label": label, "measure_type": "area",
        "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "bbox": [x0, y0, x1, y1],
        "depth_stats": {"median_m": depth} if depth else None, "is_confirmed": False,
    }


PHOTO = {"id": "p1", "image_width": 1000, "image_height": 800, "image_meta": {}, "measurement": {}}
WALL = rect("wall", 0.1, 0.1, 0.9, 0.9, "wall")          # 800 × 640 px
DOOR = rect("door", 0.45, 0.5, 0.55, 0.9, "door")         # 100 × 320 px
WINDOW = rect("window", 0.2, 0.3, 0.3, 0.45, "window")    # 100 × 120 px
RAILING = rect("railing", 0.6, 0.4, 0.9, 0.45, "railing")  # 300 px long


def by_id(segments):
    return {s["id"]: s for s in segments}


def test_standard_door_height_sets_the_scale():
    segments, scale = measure_photo(PHOTO, [WALL, DOOR, WINDOW, RAILING])
    m = 2.1 / 320  # metres per pixel from the door

    assert scale.source == "reference" and "door" in scale.detail
    s = by_id(segments)
    assert s["door"]["area_sqm"] == pytest.approx(round(100 * 320 * m**2, 2))   # 2.1 m × 0.66 m
    assert s["wall"]["area_sqm"] == pytest.approx(round(800 * 640 * m**2, 2))
    assert s["railing"]["length_m"] == pytest.approx(round(300 * m, 2))
    assert s["railing"]["area_sqm"] is None


def test_walls_are_net_of_windows_and_doors_inside_them():
    s = by_id(measure_photo(PHOTO, [WALL, DOOR, WINDOW])[0])

    openings = s["door"]["area_sqm"] + s["window"]["area_sqm"]
    assert s["wall"]["openings_sqm"] == pytest.approx(openings, abs=0.01)
    assert s["wall"]["net_area_sqm"] == pytest.approx(s["wall"]["area_sqm"] - openings, abs=0.01)


def test_openings_outside_the_wall_are_not_deducted():
    outside = rect("window", 0.92, 0.2, 0.98, 0.3, "far-window")
    s = by_id(measure_photo(PHOTO, [WALL, DOOR, outside])[0])
    assert s["wall"]["openings_sqm"] == s["door"]["area_sqm"]


def test_user_measurement_overrides_standard_sizes():
    photo = {**PHOTO, "measurement": {"reference": {"segment_id": "door", "dimension": "height", "metres": 2.4}}}

    segments, scale = measure_photo(photo, [WALL, DOOR])

    assert scale.source == "user" and "2.4 m" in scale.detail
    assert by_id(segments)["door"]["area_sqm"] == pytest.approx(round(100 * 320 * (2.4 / 320) ** 2, 2))


def test_user_measurement_by_width():
    photo = {**PHOTO, "measurement": {"reference": {"segment_id": "wall", "dimension": "width", "metres": 12}}}
    s = by_id(measure_photo(photo, [WALL])[0])
    assert s["wall"]["area_sqm"] == pytest.approx(12 * 9.6)  # 800 px = 12 m, so 640 px = 9.6 m


def test_reference_to_a_deleted_region_is_ignored():
    photo = {**PHOTO, "measurement": {"reference": {"segment_id": "gone", "dimension": "height", "metres": 3}}}
    assert resolve_scale(photo, [WALL, DOOR]).source == "reference"


def test_windows_are_used_when_there_is_no_door():
    scale = resolve_scale(PHOTO, [WALL, WINDOW])
    assert scale.source == "reference" and "window" in scale.detail
    assert scale.metres_per_px == pytest.approx(1.2 / 120)


def test_depth_model_is_used_without_doors_or_windows():
    photo = {**PHOTO, "measurement": {"focal_length_px": 1000, "focal_source": "model"}}
    near_wall = {**WALL, "depth_stats": {"median_m": 8.0}}

    segments, scale = measure_photo(photo, [near_wall, RAILING])

    assert scale.source == "depth"
    assert by_id(segments)["wall"]["area_sqm"] == pytest.approx(round(800 * 640 * (8 / 1000) ** 2, 2))


def test_assumed_distance_is_the_last_resort_and_flagged():
    segments, scale = measure_photo(PHOTO, [WALL])
    assert scale.source == "assumed" and "add a measurement" in scale.detail


def test_focal_length_prefers_model_then_exif_then_typical_phone():
    assert focal_length_px({**PHOTO, "measurement": {"focal_length_px": 900, "focal_source": "model"}}) == 900
    assert focal_length_px({**PHOTO, "image_meta": {"focal_length_35mm": 28}}) == pytest.approx(28 / 36 * 1000)
    assert focal_length_px(PHOTO) == pytest.approx(26 / 36 * 1000)


def test_point_in_polygon():
    square = [[0, 0], [1, 0], [1, 1], [0, 1]]
    assert point_in_polygon(0.5, 0.5, square) and not point_in_polygon(1.5, 0.5, square)
