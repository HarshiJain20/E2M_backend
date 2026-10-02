"""Estimate (bill of quantities) response and request models."""
import uuid

from pydantic import BaseModel, Field, model_validator


class PurchaseItem(BaseModel):
    item: str            # Paint, Primer, Tiles, Slabs, Sheets, Cement paint
    amount: float
    unit: str
    packs: int | None = None
    pack: str | None = None


class WhereItem(BaseModel):
    label: str
    name: str
    count: int


class EstimateLine(BaseModel):
    material_id: uuid.UUID
    name: str
    category: str
    unit: str
    sor_code: str | None
    rate_source: str | None
    color: str | None
    where: list[WhereItem]
    segment_ids: list[uuid.UUID]
    measured_qty: float
    wastage_factor: float
    quantity: float
    purchase: list[PurchaseItem]
    material_rate: float
    labor_rate: float
    catalog_material_rate: float
    catalog_labor_rate: float
    rate_changed: bool
    material_cost: float
    labor_cost: float
    total: float


class CategoryTotal(BaseModel):
    category: str
    material_cost: float
    labor_cost: float
    total: float


class VariantEstimate(BaseModel):
    variant_id: uuid.UUID
    name: str
    lines: list[EstimateLine]
    categories: list[CategoryTotal]
    material_total: float
    labor_total: float
    subtotal: float
    include_gst: bool
    gst_rate: float
    gst: float
    grand_total: float
    regions_without_material: int
    regions_not_counted: int


class EstimateOut(BaseModel):
    project_id: uuid.UUID
    include_gst: bool
    gst_rate: float
    variants: list[VariantEstimate]


class RateUpdate(BaseModel):
    """This project's own rate for a material (₹ per m² or running metre)."""
    material_rate: float | None = Field(default=None, ge=0, le=1_000_000)
    labor_rate: float | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def at_least_one(self):
        if self.material_rate is None and self.labor_rate is None:
            raise ValueError("Give a material rate, a labour rate, or both.")
        return self


class EstimateSettings(BaseModel):
    include_gst: bool
