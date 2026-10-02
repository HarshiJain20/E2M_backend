"""
Rules for projects with several photos (views).

- A project's status is derived from its photos, so it never goes stale.
- Each elevation (front, left, ...) has exactly one primary photo; only primaries count toward
  whole-house totals, so two photos of the same side are never added together.
"""
from app.domain import ProjectStatus


def project_status(photos: list[dict]) -> str:
    statuses = {photo["status"] for photo in photos}
    for status in (ProjectStatus.PROCESSING, ProjectStatus.REVIEW, ProjectStatus.FAILED):
        if status in statuses:
            return status
    return ProjectStatus.UPLOADED


def primary_changes(photos: list[dict]) -> tuple[list[str], list[str]]:
    """Photo ids to unset and to set so every elevation has exactly one primary.

    Keeps an existing primary where there is one (the oldest if several), otherwise promotes the
    oldest photo of that elevation. Apply the unsets before the sets (unique index).
    """
    by_elevation: dict[str, list[dict]] = {}
    for photo in sorted(photos, key=lambda p: str(p["created_at"])):
        by_elevation.setdefault(photo["elevation"], []).append(photo)

    unset, promote = [], []
    for group in by_elevation.values():
        primaries = [p for p in group if p["is_primary"]]
        keep = primaries[0] if primaries else group[0]
        unset += [str(p["id"]) for p in primaries if p is not keep]
        if not keep["is_primary"]:
            promote.append(str(keep["id"]))
    return unset, promote


def whole_house_totals(photos: list[dict], segments: list[dict]) -> list[dict]:
    """Totals per element type across the primary photo of each elevation."""
    counted = {str(p["id"]) for p in photos if p["is_primary"]}
    totals: dict[str, dict] = {}
    for segment in segments:
        if str(segment["photo_id"]) not in counted:
            continue
        is_length = segment["measure_type"] == "length"
        entry = totals.setdefault(segment["label"], {
            "label": segment["label"], "measure_type": segment["measure_type"], "total": 0.0, "count": 0,
        })
        entry["total"] += (segment.get("length_m") if is_length else segment.get("area_sqm")) or 0.0
        entry["count"] += 1
    for entry in totals.values():
        entry["total"] = round(entry["total"], 2)
    return list(totals.values())
