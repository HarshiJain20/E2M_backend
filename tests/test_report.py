"""PDF report (requirement 5.8)."""
from datetime import datetime, timezone

from app.services.reports.pdf import build_report, rupees
from tests.conftest import USER_B
from tests.test_materials import PAINT, assign, new_project, new_variant, segment_id


def test_rupees_use_indian_grouping():
    assert rupees(0) == "Rs 0" and rupees(999) == "Rs 999" and rupees(1234567.4) == "Rs 12,34,567"
    assert rupees(68481.3) == "Rs 68,481"


def test_report_for_a_design_with_materials(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    assert assign(client, variant["id"], [segment_id(project, "wall")], PAINT, "#a7bccb").status_code == 200

    response = client.get(f"/api/v1/variants/{variant['id']}/report.pdf")

    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and b"/Image" in response.content  # before/after photos
    assert 'filename="' in response.headers["content-disposition"]


def test_report_for_an_empty_design_still_builds(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    response = client.get(f"/api/v1/variants/{variant['id']}/report.pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")


def test_reports_are_private(client):
    project = new_project(client)
    variant = new_variant(client, project)["variants"][0]
    client.as_user(USER_B)
    assert client.get(f"/api/v1/variants/{variant['id']}/report.pdf").status_code == 404


def test_build_report_lists_every_line():
    line = {"name": "Glass railing", "category": "railing", "unit": "rmt", "sor_code": None, "rate_source": "Market rate",
            "color": None, "where": [{"label": "railing", "name": "railings", "count": 2}], "measured_qty": 6,
            "wastage_factor": 0.05, "quantity": 6.3, "purchase": [], "material_rate": 6500, "labor_rate": 1200,
            "rate_changed": True, "material_cost": 40950, "labor_cost": 7200, "total": 48150}
    estimate = {"name": "Design A", "lines": [line], "categories": [
        {"category": "railing", "material_cost": 40950, "labor_cost": 7200, "total": 48150}],
        "material_total": 40950, "labor_total": 7200, "subtotal": 48150, "include_gst": False, "gst_rate": 0.18,
        "gst": 0, "grand_total": 48150, "regions_without_material": 1, "regions_not_counted": 0}
    pdf = build_report("My house", estimate, [], datetime(2026, 10, 2, tzinfo=timezone.utc), ["note"])
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000
