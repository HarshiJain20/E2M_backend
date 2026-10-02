# How estimation works

The estimate is built in three steps: **outline → size → quantity and cost**. All three are
recomputed on every request, so any correction the user makes flows straight through.

## 1. Outlines (AI)

Grounding DINO finds each building part from a text prompt ("house wall", "window", "door",
"pillar", …) and SAM traces its outline. Outlines are stored as polygons in normalised image
coordinates. The roof and trees are detected in a separate pass only to be **cut out** of wall
outlines, so a roof is never painted or priced as wall. The user reviews every outline and can
relabel, delete or size it.

## 2. Size: from pixels to metres

A photo has no built-in scale, so each photo gets one **scale** (metres per pixel), chosen from the
best evidence available, in this order:

| # | Source | How | Shown to the user as |
|---|--------|-----|----------------------|
| 1 | **User measurement** | The user measures one region, e.g. "the door is 2.1 m tall": metres ÷ that region's pixel height | "Your measurement: …" |
| 2 | **Reference size** | Standard heights of detected doors (2.1 m) or, failing that, windows (1.2 m); median over all of them | "Standard door height 2.1 m (2 in the photo)" |
| 3 | **Depth / perspective** | Depth Pro estimates each region's distance *Z* and the camera's focal length *f* (px); pinhole camera: metres per px = *Z* ÷ *f*, per region | "Estimated from the depth model's distance…" |
| 4 | **Assumed** | 10 m camera distance with a typical phone focal length (26 mm equivalent) | "Assumed … add a measurement for accuracy" (flagged) |

Then for each region:

- **Area** (walls, pillars, balconies, parapets, gates, windows, doors) = polygon area in px² × (metres per px)².
- **Length** (railings, roof edges) = the longer side of the region's box × metres per px.
- **Walls are net:** each window and door is deducted from the wall that contains its centre.
- **Exact sizes win:** if the user typed a size for a region (width × height, area or length), it
  replaces the estimate.
- **No double counting:** if several photos show the same side, only the one marked counted
  (primary) is included in totals and in the estimate.

## 3. Quantity and cost

For every material in a design, the regions using it are added up:

```
measured     = Σ region sizes (m² or running m)
quantity     = measured × (1 + wastage)            wastage per material, e.g. 5 % paint, 10 % tiles
material ₹   = quantity × material rate            you buy the wastage
labour ₹     = measured × labour rate              labour is paid on the actual surface
line total   = material ₹ + labour ₹
subtotal     = Σ line totals
GST          = subtotal × 18 %                     can be switched off
grand total  = subtotal + GST
```

**What to buy** is derived from the quantity and the catalogue's coverage and unit sizes:
paint litres = quantity × litres per m² (two coats), rounded up to whole cans; primer = 0.09 L per
m² of measured surface; cement-based products in kg and bags; tiles, stone slabs and cladding
sheets as counts of their unit size.

**Rates** are per m² or running metre, split into material and labour. Three items are based on
CPWD DSR 2021 (13.46.1 acrylic exterior paint, 13.45.1 textured paint, 13.1 cement plaster); the
others are indicative market rates. The user can change any rate **for one project** (the shared
catalogue is not touched) and reset it later.

## Worked example

A front wall of 60 m² with 10 m² of windows and doors, plus pillars of 10 m², both in acrylic
exterior paint (material ₹95/m², labour ₹65/m², 5 % wastage, 0.167 L/m² for two coats):

| Step | Value |
|------|-------|
| Wall, net of openings | 60 − 10 = **50 m²** |
| Measured (wall + pillars) | 50 + 10 = **60 m²** |
| Quantity with wastage | 60 × 1.05 = **63 m²** |
| Material | 63 × ₹95 = **₹5,985** |
| Labour | 60 × ₹65 = **₹3,900** |
| Line total | **₹9,885** |
| Paint to buy | 63 × 0.167 ≈ 10.5 L → **one 20 L can** |
| Primer | 60 × 0.09 = **5.4 L** |

These figures are checked by the automated test `tests/test_estimate.py`.

## Where the numbers appear

The Review page shows sizes per region and whole-house totals; the Estimate page shows the full
bill of quantities with editable rates; the PDF report carries the same estimate, the before/after
images and a summary of this method.
