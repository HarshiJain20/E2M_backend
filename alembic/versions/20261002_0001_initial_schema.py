"""Create the E2M schema (projects, jobs, segments, materials, variants, BoQ).

Revision ID: 20261002_0001
Revises:
Create Date: 2026-10-02

Row Level Security is enabled on every table with no policies. Supabase exposes the
public schema through its Data API to anyone holding the publishable key; with RLS on
and no policies, that API returns nothing. The backend connects as the database owner,
which bypasses RLS, and enforces per-user access itself.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    "projects",
    "jobs",
    "segments",
    "materials",
    "design_variants",
    "segment_materials",
    "project_rate_overrides",
    "boq_items",
)


def _timestamp(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("original_image_path", sa.String(512), nullable=False),
        sa.Column("working_image_path", sa.String(512), nullable=False),
        sa.Column("thumbnail_path", sa.String(512), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("image_meta", sa.JSON(), nullable=False),
        sa.Column("quality_report", sa.JSON(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_meta", sa.JSON(), nullable=False),
        _timestamp("created_at"),
        _timestamp("started_at", nullable=True),
        _timestamp("finished_at", nullable=True),
    )
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])

    op.create_table(
        "segments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("polygon", sa.JSON(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.Column("measure_type", sa.String(8), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("length_m", sa.Float(), nullable=True),
        sa.Column("scale_source", sa.String(16), nullable=True),
        sa.Column("user_dimension", sa.JSON(), nullable=True),
        sa.Column("depth_stats", sa.JSON(), nullable=True),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False),
        _timestamp("created_at"),
    )
    op.create_index("ix_segments_project_id", "segments", ["project_id"])

    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sor_code", sa.String(32), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("material_rate", sa.Float(), nullable=False),
        sa.Column("labor_rate", sa.Float(), nullable=False),
        sa.Column("wastage_factor", sa.Float(), nullable=False),
        sa.Column("coverage", sa.JSON(), nullable=True),
        sa.Column("unit_size", sa.JSON(), nullable=True),
        sa.Column("suitability", sa.Text(), nullable=True),
        sa.Column("maintenance", sa.Text(), nullable=True),
        sa.Column("durability", sa.Text(), nullable=True),
        sa.Column("texture_ref", sa.String(512), nullable=True),
        sa.Column("render_prompt", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "design_variants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("rendered_image_path", sa.String(512), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )
    op.create_index("ix_design_variants_project_id", "design_variants", ["project_id"])

    op.create_table(
        "segment_materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "variant_id",
            sa.Uuid(),
            sa.ForeignKey("design_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_id", sa.Uuid(), sa.ForeignKey("segments.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("material_id", sa.Uuid(), sa.ForeignKey("materials.id"), nullable=False),
        sa.UniqueConstraint("variant_id", "segment_id"),
    )
    op.create_index("ix_segment_materials_variant_id", "segment_materials", ["variant_id"])

    op.create_table(
        "project_rate_overrides",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("material_id", sa.Uuid(), sa.ForeignKey("materials.id"), nullable=False),
        sa.Column("material_rate", sa.Float(), nullable=True),
        sa.Column("labor_rate", sa.Float(), nullable=True),
        sa.UniqueConstraint("project_id", "material_id"),
    )
    op.create_index("ix_project_rate_overrides_project_id", "project_rate_overrides", ["project_id"])

    op.create_table(
        "boq_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "variant_id",
            sa.Uuid(),
            sa.ForeignKey("design_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_id", sa.Uuid(), sa.ForeignKey("segments.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("material_id", sa.Uuid(), sa.ForeignKey("materials.id"), nullable=True),
        sa.Column("material_name", sa.String(160), nullable=False),
        sa.Column("sor_code", sa.String(32), nullable=True),
        sa.Column("measured_qty", sa.Float(), nullable=False),
        sa.Column("wastage_factor", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("quantity_unit", sa.String(8), nullable=False),
        sa.Column("purchase_qty", sa.JSON(), nullable=True),
        sa.Column("material_rate", sa.Float(), nullable=False),
        sa.Column("labor_rate", sa.Float(), nullable=False),
        sa.Column("material_cost", sa.Float(), nullable=False),
        sa.Column("labor_cost", sa.Float(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
    )
    op.create_index("ix_boq_items_variant_id", "boq_items", ["variant_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
