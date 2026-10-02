# Limitations

This is a prototype. The estimate is **advisory**: good for planning and comparing designs, not a
substitute for measuring on site and getting contractor quotes.

## Measurement
- **Sizes come from photos.** Accuracy depends on the scale source: a user measurement is best;
  standard door/window sizes are good when those openings are standard; depth-based and assumed
  scales can be well off. The scale source is always shown, and assumed scales are flagged.
- **One scale per photo** (or per region with depth). Strong perspective, such as a wall photographed at a
  steep angle, makes far parts look smaller, so their area is under-estimated. Photos taken straight
  on give the best results.
- **Only what is visible is measured.** Surfaces hidden by trees, cars or other buildings, and sides
  without a photo, are not included. Trees are cut out of walls, so the wall behind them is missing.
- **No 3D model.** Each view is measured separately; corners, returns and recesses are not
  reconstructed.

## Detection
- The open-vocabulary detector (Grounding DINO tiny + SAM base, chosen to fit a free GPU) misses
  or mislabels some parts, especially small ones (railings, roof edges, parapets) and unusual
  architecture. Every result must be **reviewed**; the Review page exists for this.
- Outlines are simplified polygons; very fine edges (mouldings, grilles) are approximated.
- Indoor or non-house photos are flagged when no wall, window or door is found.

## Cost
- **Rates are indicative.** Only three items follow CPWD DSR 2021; the rest are market estimates and
  vary by city and year. Rates can be edited per project.
- Not included: surface preparation and repairs (crack filling, waterproofing, removing old
  cladding), scaffolding, transport, contractor margin, regional price indices. Wastage is a fixed
  percentage per material.
- GST is applied at a single rate (18 %) to the whole subtotal.

## Redesign images
- The **standard** preview overlays procedural textures at real-world scale with the photo's own
  lighting. It shows colour, pattern and scale, not exact product appearance.
- The **photorealistic** mode (SDXL) can invent small details inside the changed regions and
  takes about a minute; it needs the GPU service running.

## Running environment
- The AI service runs on a free Kaggle GPU through a temporary tunnel: its address changes every
  session and sessions time out. When it is down, new analyses and photorealistic renders fail
  with a clear message; everything else keeps working.
- Background jobs run inside the API process; a restart during an analysis marks that job as
  failed (it can be re-run). Production would use a job queue.
- Some model licences restrict commercial use; see [open-source components](open-source.md).
