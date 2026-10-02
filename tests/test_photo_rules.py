from app.services.photos import primary_changes, project_status, whole_house_totals


def photo(pid, elevation, primary, created, status="review"):
    return {"id": pid, "elevation": elevation, "is_primary": primary, "created_at": created, "status": status}


def test_status_prefers_processing_then_review_then_failed():
    assert project_status([]) == "uploaded"
    assert project_status([photo("a", "front", True, 1, "failed"), photo("b", "left", True, 2, "review")]) == "review"
    assert project_status([photo("a", "front", True, 1, "review"), photo("b", "left", True, 2, "processing")]) == "processing"
    assert project_status([photo("a", "front", True, 1, "failed")]) == "failed"


def test_side_without_primary_promotes_oldest():
    unset, promote = primary_changes([photo("new", "left", False, 2), photo("old", "left", False, 1)])
    assert (unset, promote) == ([], ["old"])


def test_extra_primaries_are_unset_keeping_oldest():
    unset, promote = primary_changes([photo("a", "front", True, 1), photo("b", "front", True, 2)])
    assert (unset, promote) == (["b"], [])


def test_totals_count_only_primary_photos():
    photos = [photo("p1", "front", True, 1), photo("p2", "front", False, 2), photo("p3", "rear", True, 3)]
    segments = [
        {"photo_id": "p1", "label": "wall", "measure_type": "area", "area_sqm": 40.0},
        {"photo_id": "p2", "label": "wall", "measure_type": "area", "area_sqm": 41.0},
        {"photo_id": "p3", "label": "wall", "measure_type": "area", "area_sqm": 30.0},
        {"photo_id": "p3", "label": "railing", "measure_type": "length", "length_m": 4.5},
    ]
    totals = {t["label"]: t for t in whole_house_totals(photos, segments)}
    assert totals["wall"] == {"label": "wall", "measure_type": "area", "total": 70.0, "count": 2, "openings_sqm": 0.0}
    assert totals["railing"]["total"] == 4.5
