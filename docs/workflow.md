# User workflow

```mermaid
graph LR
    A[Sign in] --> B[New project: upload photos]
    B --> C[Automatic analysis]
    C --> D[Review surfaces]
    D --> E[Choose materials]
    E --> F[Estimate]
    F --> G[PDF report]
    D -. edit any time .-> E
    E -. compare designs .-> F
```

1. **Sign in.** Email and password (Supabase Auth). Each user sees only their own projects.

2. **Create a project and upload photos.** Up to 8 photos of one house, each tagged as a view
   (front, left side, right side, rear, other). Every photo is checked for resolution, blur,
   sharpness, lighting, detail and framing; unusable photos are rejected with advice on how to retake them. More
   photos can be added later. If two photos show the same side, one is marked **counted**
   (primary) so its areas are not added twice.

3. **Automatic analysis.** Each photo is sent to the AI service, which finds walls, windows, doors,
   balconies, pillars, parapets, gates, roof edges and railings and outlines them. Progress is
   shown; photos with no house in them are flagged.

4. **Review surfaces.** The outlines are drawn on the photo. The user can:
   - relabel a region (e.g. "pillar" → "wall") or delete a wrong one;
   - give one real measurement (e.g. "this door is 2.1 m tall") to set the scale for the whole photo;
   - type an exact size for any region (width × height, area, or length);
   - then confirm the photo.
   Areas update immediately, in m² and sq ft, with whole-house totals.

5. **Choose materials.** Create a design (Design A, B, …) or duplicate one to compare. Select
   regions on the photo or by type; only materials that suit all selected parts are offered, each
   with suitability, maintenance and durability notes and its rate. Pick a colour where the
   material takes one, and apply. The photo updates with the material at real-world scale; a
   before/after slider compares it with the original. Optionally, **Make it photorealistic (AI)**
   produces a photorealistic render on the GPU.

6. **Estimate.** For each design: materials, where they are used, measured size, quantity with
   wastage, what to buy (litres and cans, bags, tiles, sheets), material and labour cost, totals
   by category, subtotal, GST (can be switched off) and grand total. Any rate can be changed for
   this project to match a quote; totals recalculate at once. Designs can be compared side by side.

7. **PDF report.** "Download PDF report" on the Estimate page produces a report with the original
   and redesigned image of each counted view, the materials, the bill of quantities, the cost
   breakdown and how the estimate was made.

Everything is saved as it changes; reopening a project continues where the user left off.
