"""
E2M Backend — SQLAlchemy ORM Models.

Phase 1 uses projects and jobs. The remaining tables define the data contract for
later phases (segments review, materials, design variants, rate overrides, BoQ)
so the schema is stable before the features that fill it are built.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


class Project(Base):
    """A renovation project created from an uploaded exterior photo."""
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)  # Supabase auth.users.id
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.UPLOADED)

    original_image_path: Mapped[str] = mapped_column(String(512))
    working_image_path: Mapped[str] = mapped_column(String(512))
    thumbnail_path: Mapped[str] = mapped_column(String(512))
    image_width: Mapped[int] = mapped_column(Integer)    # working image size, px
    image_height: Mapped[int] = mapped_column(Integer)
    image_meta: Mapped[dict] = mapped_column(JSON, default=dict)      # EXIF focal length, original size
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict)  # checks shown to the user

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Job.created_at"
    )
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    variants: Mapped[list["DesignVariant"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    rate_overrides: Mapped[list["ProjectRateOverride"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Job(Base):
    """A background pipeline run for a project (analysis now; rendering later)."""
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="analyze")
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_meta: Mapped[dict] = mapped_column(JSON, default=dict)  # timings, model info, mock flag

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="jobs")


class Segment(Base):
    """A detected or user-drawn architectural element (wall, window, railing, ...)."""
    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(32))          # wall, window, door, balcony, ...
    source: Mapped[str] = mapped_column(String(16), default="auto")  # auto | user
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    polygon: Mapped[list] = mapped_column(JSON, default=list)  # [[x, y], ...] normalised 0-1
    bbox: Mapped[list] = mapped_column(JSON, default=list)     # [x0, y0, x1, y1] normalised 0-1
    measure_type: Mapped[str] = mapped_column(String(8), default="area")  # area | length
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # depth|reference|user
    user_dimension: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"axis": "height", "m": 2.1}
    depth_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="segments")


class Material(Base):
    """Catalog entry with rates and the guidance homeowners need to choose it."""
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sor_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # CPWD DSR / Gujarat SOR
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(32))  # paint, texture, stone_cladding, tiles, ...
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(8))       # sqm | rmt
    material_rate: Mapped[float] = mapped_column(Float)  # ₹ per unit
    labor_rate: Mapped[float] = mapped_column(Float)     # ₹ per unit
    wastage_factor: Mapped[float] = mapped_column(Float, default=0.10)
    coverage: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"sqm_per_litre": 10, "coats": 2}
    unit_size: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"tile_w_m": 0.6, "tile_h_m": 0.3}
    suitability: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    durability: Mapped[str | None] = mapped_column(Text, nullable=True)
    texture_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    render_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DesignVariant(Base):
    """One named combination of materials for a project ("Design A", "Design B")."""
    __tablename__ = "design_variants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    rendered_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="variants")
    assignments: Mapped[list["SegmentMaterial"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )
    boq_items: Mapped[list["BoQItem"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )


class SegmentMaterial(Base):
    """Material applied to a segment within a design variant."""
    __tablename__ = "segment_materials"
    __table_args__ = (UniqueConstraint("variant_id", "segment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_variants.id", ondelete="CASCADE"), index=True
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("segments.id", ondelete="CASCADE"))
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))

    variant: Mapped[DesignVariant] = relationship(back_populates="assignments")


class ProjectRateOverride(Base):
    """User-edited material/labour rate for one project (requirement 5.7)."""
    __tablename__ = "project_rate_overrides"
    __table_args__ = (UniqueConstraint("project_id", "material_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    material_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    labor_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped[Project] = relationship(back_populates="rate_overrides")


class BoQItem(Base):
    """Bill of Quantities line for a variant: quantity, material and labour cost."""
    __tablename__ = "boq_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_variants.id", ondelete="CASCADE"), index=True
    )
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("segments.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(32))
    material_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials.id"), nullable=True)
    material_name: Mapped[str] = mapped_column(String(160))
    sor_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    measured_qty: Mapped[float] = mapped_column(Float)      # sqm or rmt before wastage
    wastage_factor: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)          # measured × (1 + wastage)
    quantity_unit: Mapped[str] = mapped_column(String(8))
    purchase_qty: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"litres": 42} / {"tiles": 310}
    material_rate: Mapped[float] = mapped_column(Float)
    labor_rate: Mapped[float] = mapped_column(Float)
    material_cost: Mapped[float] = mapped_column(Float)
    labor_cost: Mapped[float] = mapped_column(Float)
    total_cost: Mapped[float] = mapped_column(Float)

    variant: Mapped[DesignVariant] = relationship(back_populates="boq_items")
