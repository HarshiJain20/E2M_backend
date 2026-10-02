"""Status values shared by the API, the pipeline and the database check constraints."""


class ProjectStatus:
    UPLOADED = "uploaded"        # image stored, not analysed yet
    PROCESSING = "processing"    # an analysis job is running
    REVIEW = "review"            # regions detected, awaiting user review
    FAILED = "failed"            # last analysis failed


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    ACTIVE = (QUEUED, RUNNING)


# Sides of the house a photo can show. One primary photo per elevation counts toward totals.
ELEVATIONS = ("front", "left", "right", "rear", "other")

MAX_PHOTOS_PER_PROJECT = 8

# Building elements the AI service detects (requirement 5.2). Railings and roof edges are
# measured by length, everything else by area.
LABELS = ("wall", "window", "door", "balcony", "pillar", "parapet", "gate", "roof_edge", "railing")
LENGTH_LABELS = ("railing", "roof_edge")


def measure_type(label: str) -> str:
    return "length" if label in LENGTH_LABELS else "area"
