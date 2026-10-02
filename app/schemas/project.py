"""API response and request models for projects, jobs and segments."""
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _as_utc(value: datetime) -> datetime:
    """Databases without timezone support return naive UTC; always emit an explicit offset."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class QualityCheckOut(BaseModel):
    id: str
    label: str
    status: str
    value: float
    message: str
    guidance: str | None = None


class QualityReportOut(BaseModel):
    usable: bool
    checks: list[QualityCheckOut]


class JobOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    status: str
    stage: str | None
    progress: int
    error: str | None
    result_meta: dict
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None


class SegmentOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    photo_id: uuid.UUID
    label: str
    source: str
    confidence: float | None
    polygon: list[list[float]]
    bbox: list[float]
    measure_type: str
    area_sqm: float | None
    length_m: float | None
    net_area_sqm: float | None = None   # walls: area minus the windows/doors inside them
    openings_sqm: float | None = None   # walls: area of those windows/doors
    scale_source: str | None
    is_confirmed: bool


class ScaleOut(BaseModel):
    source: Literal["user", "reference", "depth", "assumed"]
    detail: str


class ReferenceOut(BaseModel):
    segment_id: uuid.UUID
    dimension: Literal["height", "width"]
    metres: float


class PhotoOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    elevation: str
    is_primary: bool
    status: str
    image_url: str | None
    thumbnail_url: str | None
    image_width: int
    image_height: int
    image_meta: dict
    quality_report: QualityReportOut
    latest_job: JobOut | None = None
    segments: list[SegmentOut] = []
    regions_confirmed: bool = False  # the user reviewed this photo's regions
    scale: ScaleOut | None = None  # how sizes in this photo were estimated
    reference: ReferenceOut | None = None  # the user's own measurement, if any
    created_at: UtcDatetime


class TotalOut(BaseModel):
    label: str
    measure_type: str
    total: float  # walls: net of openings
    count: int
    openings_sqm: float = 0.0


class ProjectSummary(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    thumbnail_url: str | None
    photo_count: int
    segment_count: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ProjectDetail(ProjectSummary):
    photos: list[PhotoOut]
    # Whole-house totals: the primary photo of each elevation only, so no side is counted twice.
    totals: list[TotalOut]


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ReferenceIn(BaseModel):
    """The user's measurement of one region, which sets the scale for the whole photo."""
    segment_id: uuid.UUID
    dimension: Literal["height", "width"]
    metres: float = Field(gt=0.1, le=100)


class SegmentUpdate(BaseModel):
    label: Literal["wall", "window", "door", "balcony", "pillar", "parapet", "gate", "roof_edge", "railing"]


class PhotoUpdate(BaseModel):
    elevation: Literal["front", "left", "right", "rear", "other"] | None = None
    is_primary: Literal[True] | None = None  # make this the counted photo for its elevation
