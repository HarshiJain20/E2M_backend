"""API response and request models for projects, jobs and segments."""
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


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
    size_source: Literal["estimated", "user"] = "estimated"
    user_size: dict | None = None       # the exact size the user entered, as given
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


class MaterialOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    name: str
    category: str
    description: str | None = None
    sor_code: str | None = None
    rate_source: str | None = None
    unit: Literal["sqm", "rmt"]
    material_rate: float
    labor_rate: float
    wastage_factor: float
    coverage: dict | None = None
    unit_size: dict | None = None
    applies_to: list[str]
    colorable: bool = False
    swatch: str | None = None
    suitability: str | None = None
    maintenance: str | None = None
    durability: str | None = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segment_id: uuid.UUID
    material_id: uuid.UUID
    color: str | None = None


class VariantOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    name: str
    assignments: list[AssignmentOut] = []
    created_at: UtcDatetime


class PhotorealOut(BaseModel):
    status: Literal["ready", "none"]  # none = not rendered yet for the current materials
    url: str | None = None


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
    variants: list[VariantOut] = []  # design options: which material goes on which region


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class VariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    copy_from: uuid.UUID | None = None  # duplicate another design's materials


class VariantUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class AssignmentIn(BaseModel):
    """Apply one material (and colour, for paints) to one or more regions."""
    segment_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    material_id: uuid.UUID
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class ReferenceIn(BaseModel):
    """The user's measurement of one region, which sets the scale for the whole photo."""
    segment_id: uuid.UUID
    dimension: Literal["height", "width"]
    metres: float = Field(gt=0.1, le=100)


class SegmentSize(BaseModel):
    """An exact size the user measured: width × height or area for surfaces, length for lines."""
    width_m: float | None = Field(default=None, gt=0, le=200)
    height_m: float | None = Field(default=None, gt=0, le=200)
    area_sqm: float | None = Field(default=None, gt=0, le=20000)
    length_m: float | None = Field(default=None, gt=0, le=500)

    @model_validator(mode="after")
    def one_complete_size(self):
        given = {k for k, v in self.model_dump().items() if v is not None}
        if given not in ({"width_m", "height_m"}, {"area_sqm"}, {"length_m"}):
            raise ValueError("Give width and height, or an area, or a length.")
        return self


class SegmentUpdate(BaseModel):
    label: Literal["wall", "window", "door", "balcony", "pillar", "parapet", "gate", "roof_edge", "railing"]


class PhotoUpdate(BaseModel):
    elevation: Literal["front", "left", "right", "rear", "other"] | None = None
    is_primary: Literal[True] | None = None  # make this the counted photo for its elevation
