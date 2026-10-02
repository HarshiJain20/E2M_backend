"""
PDF report for one design (requirement 5.8): before/after images, materials, quantities and cost.

`build_report` is a pure function of already-computed data (the estimate from
services.estimate and the images per view), so it is tested without storage or the AI service.
Built with ReportLab's standard fonts; they have no rupee glyph, so amounts are written "Rs".
"""
import io
from datetime import datetime

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

INK = colors.HexColor("#1c1917")
MUTED = colors.HexColor("#57534e")
LINE = colors.HexColor("#d6d3d1")
SOFT = colors.HexColor("#f5f5f4")
ACCENT = colors.HexColor("#b45309")

UNIT_NAMES = {"sqm": "m²", "rmt": "running m"}
CATEGORY_NAMES = {
    "paint": "Paint", "texture": "Texture", "plaster": "Plaster", "stone_cladding": "Stone cladding",
    "tiles": "Tiles", "panels": "Panels", "railing": "Railings",
}
PAGE_WIDTH = A4[0] - 36 * mm


def rupees(value: float) -> str:
    """Indian digit grouping: Rs 12,34,567."""
    whole = str(round(value))
    sign, whole = ("-", whole[1:]) if whole.startswith("-") else ("", whole)
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups + [tail])
    return f"{sign}Rs {whole}"


def number(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=INK)
    return {
        "title": ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=18, leading=22),
        "h2": ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=16,
                             spaceBefore=10, spaceAfter=6),
        "body": body,
        "muted": ParagraphStyle("muted", parent=body, textColor=MUTED, fontSize=8, leading=11),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=10.5),
        "num": ParagraphStyle("num", parent=body, fontSize=8, leading=10.5, alignment=TA_RIGHT),
        "big": ParagraphStyle("big", parent=body, fontName="Helvetica-Bold", fontSize=16, leading=20,
                              textColor=ACCENT, alignment=TA_RIGHT),
    }


def _image(data: bytes, width: float, max_px: int = 1400) -> Image:
    """A JPEG flowable, downscaled so the PDF stays small."""
    with PILImage.open(io.BytesIO(data)) as source:
        picture = source.convert("RGB")
    picture.thumbnail((max_px, max_px))
    buffer = io.BytesIO()
    picture.save(buffer, format="JPEG", quality=82)
    buffer.seek(0)
    return Image(buffer, width=width, height=width * picture.height / picture.width)


def _table(rows, widths, header=True, numeric_from=None) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK)]
    if numeric_from is not None:
        style.append(("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def _where(line: dict) -> str:
    return ", ".join(f"{w['count']} {w['name']}" for w in line["where"])


def _buy(line: dict) -> str:
    parts = []
    for item in line["purchase"]:
        text = f"{item['item']}: {number(item['amount'])} {item['unit']}"
        if item.get("packs"):
            text += f" ({item['packs']} × {item['pack']})"
        parts.append(text)
    return "<br/>".join(parts) or "—"


def build_report(
    project_name: str,
    estimate: dict,
    views: list[dict],
    generated_at: datetime,
    notes: list[str] | None = None,
) -> bytes:
    """
    `estimate`: one design's estimate (schemas.estimate.VariantEstimate as a dict).
    `views`: [{"title", "scale", "before": jpeg, "after": jpeg, "after_kind": "Standard"|"Photorealistic (AI)"}].
    """
    s = _styles()
    story = []

    # ── Cover / summary ──
    story += [
        Paragraph("Exterior renovation estimate", s["muted"]),
        Paragraph(project_name, s["title"]),
        Paragraph(f"Design: <b>{estimate['name']}</b> &nbsp;·&nbsp; {generated_at:%d %b %Y}", s["body"]),
        Spacer(1, 6 * mm),
    ]
    gst_label = f"GST {estimate['gst_rate'] * 100:g}%" if estimate["include_gst"] else "GST (not included)"
    summary = [
        [Paragraph("Materials", s["cell"]), Paragraph(rupees(estimate["material_total"]), s["num"])],
        [Paragraph("Labour", s["cell"]), Paragraph(rupees(estimate["labor_total"]), s["num"])],
        [Paragraph("Subtotal", s["cell"]), Paragraph(rupees(estimate["subtotal"]), s["num"])],
        [Paragraph(gst_label, s["cell"]), Paragraph(rupees(estimate["gst"]), s["num"])],
        [Paragraph("<b>Estimated total</b>", s["body"]), Paragraph(rupees(estimate["grand_total"]), s["big"])],
    ]
    table = _table(summary, [PAGE_WIDTH * 0.6, PAGE_WIDTH * 0.4], header=False)
    table.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.8, INK), ("VALIGN", (0, -1), (-1, -1), "MIDDLE")]))
    story.append(table)
    warnings = []
    if estimate["regions_without_material"]:
        warnings.append(f"{estimate['regions_without_material']} detected region(s) have no material and are not priced.")
    if estimate["regions_not_counted"]:
        warnings.append(f"{estimate['regions_not_counted']} region(s) are on a second photo of the same side "
                        "and are not counted twice.")
    for text in warnings:
        story.append(Paragraph(text, s["muted"]))

    # ── Before / after ──
    if views:
        story.append(Paragraph("Before and after", s["h2"]))
        half = (PAGE_WIDTH - 6 * mm) / 2
        for view in views:
            pair = Table(
                [[Paragraph("Original", s["muted"]), Paragraph(f"Redesigned ({view['after_kind']})", s["muted"])],
                 [_image(view["before"], half), _image(view["after"], half)]],
                colWidths=[half + 3 * mm, half + 3 * mm],
            )
            pair.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                                      ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(KeepTogether([
                Paragraph(f"<b>{view['title']}</b>", s["body"]),
                Paragraph(f"Scale: {view['scale']}", s["muted"]),
                Spacer(1, 2 * mm), pair, Spacer(1, 5 * mm),
            ]))

    # ── Materials ──
    lines = estimate["lines"]
    story.append(Paragraph("Materials", s["h2"]))
    if not lines:
        story.append(Paragraph("No materials have been chosen for this design yet.", s["body"]))
    else:
        rows = [[Paragraph(f"<b>{h}</b>", s["cell"]) for h in ("Material", "Colour", "Used on", "Rate source")]]
        for line in lines:
            source = line["rate_source"] or "—"
            if line["sor_code"]:
                source += f", item {line['sor_code']}"
            if line["rate_changed"]:
                source += " (rate changed for this project)"
            colour = Table([[""]], colWidths=[8 * mm], rowHeights=[4 * mm])
            if line["color"]:
                colour.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(line["color"])),
                                            ("BOX", (0, 0), (-1, -1), 0.4, LINE)]))
            rows.append([Paragraph(line["name"], s["cell"]), colour if line["color"] else Paragraph("—", s["cell"]),
                         Paragraph(_where(line), s["cell"]), Paragraph(source, s["cell"])])
        story.append(_table(rows, [PAGE_WIDTH * w for w in (0.32, 0.1, 0.28, 0.3)]))

        # ── Bill of quantities ──
        story.append(Paragraph("Quantities and cost", s["h2"]))
        rows = [[Paragraph(f"<b>{h}</b>", s["num"] if i >= 2 else s["cell"]) for i, h in enumerate(
            ("Material", "To buy", "Measured", "With wastage", "Rate / unit<br/>material + labour",
             "Material", "Labour", "Total"))]]
        for line in lines:
            unit = UNIT_NAMES.get(line["unit"], line["unit"])
            rows.append([
                Paragraph(line["name"], s["cell"]),
                Paragraph(_buy(line), s["cell"]),
                Paragraph(f"{number(line['measured_qty'])} {unit}", s["num"]),
                Paragraph(f"{number(line['quantity'])} {unit}<br/>(+{line['wastage_factor'] * 100:g}%)", s["num"]),
                Paragraph(f"{rupees(line['material_rate'])} + {rupees(line['labor_rate'])}", s["num"]),
                Paragraph(rupees(line["material_cost"]), s["num"]),
                Paragraph(rupees(line["labor_cost"]), s["num"]),
                Paragraph(f"<b>{rupees(line['total'])}</b>", s["num"]),
            ])
        story.append(_table(rows, [PAGE_WIDTH * w for w in (0.17, 0.2, 0.1, 0.11, 0.14, 0.09, 0.09, 0.1)]))

        rows = [[Paragraph(f"<b>{h}</b>", s["num"] if i else s["cell"])
                 for i, h in enumerate(("Category", "Material", "Labour", "Total"))]]
        for category in estimate["categories"]:
            rows.append([Paragraph(CATEGORY_NAMES.get(category["category"], category["category"]), s["cell"]),
                         *(Paragraph(rupees(category[k]), s["num"]) for k in ("material_cost", "labor_cost", "total"))])
        rows.append([Paragraph("<b>Subtotal</b>", s["cell"]),
                     Paragraph(rupees(estimate["material_total"]), s["num"]),
                     Paragraph(rupees(estimate["labor_total"]), s["num"]),
                     Paragraph(f"<b>{rupees(estimate['subtotal'])}</b>", s["num"])])
        rows.append([Paragraph(gst_label, s["cell"]), "", "", Paragraph(rupees(estimate["gst"]), s["num"])])
        rows.append([Paragraph("<b>Estimated total</b>", s["cell"]), "", "",
                     Paragraph(f"<b>{rupees(estimate['grand_total'])}</b>", s["num"])])
        story.append(KeepTogether([Paragraph("By category", s["h2"]),
                                   _table(rows, [PAGE_WIDTH * w for w in (0.4, 0.2, 0.2, 0.2)])]))

    # ── How it was estimated ──
    story.append(Paragraph("How this estimate was made", s["h2"]))
    for text in notes or []:
        story.append(Paragraph(f"• {text}", s["muted"]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{project_name} — {estimate['name']}", author="E2M")

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9 * mm, "Indicative estimate. Check measurements and rates on site before ordering.")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


METHOD_NOTES = [
    "Building parts (walls, windows, doors, pillars, railings, …) were detected in each photo by AI "
    "(Grounding DINO + SAM) and reviewed by the user.",
    "Sizes come from the outlines and one scale per photo: the user's own measurement if given, else the "
    "standard height of a door (2.1 m) or window (1.2 m) in the photo, else a depth model's distance to "
    "each surface, else an assumed 10 m camera distance. Exact sizes typed in by the user replace estimates.",
    "Wall areas are net of the windows and doors inside them. Railings and roof edges are measured in running metres.",
    "Only the counted (primary) photo of each side of the house is included, so nothing is priced twice.",
    "Quantity = measured size × (1 + wastage). Material cost is charged on the quantity, labour on the measured size.",
    "Rates: CPWD DSR 2021 items where available, otherwise indicative market rates; rates may have been "
    "adjusted for this project.",
    "Limitations: sizes are estimated from photos, so accuracy depends on the scale used (best with a measurement); "
    "hidden or occluded surfaces are not measured, and surface preparation or repairs are not included.",
]
