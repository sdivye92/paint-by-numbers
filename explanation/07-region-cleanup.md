# 07 · Region cleanup: making every region paintable

## What it does and why it is here

Both methods can leave regions that cannot really be painted: a patch of 20 pixels, or a long sliver one pixel wide. Cleanup repaints every such region with the colour of a neighbour until **every connected region is big enough and wide enough**. This is what turns a good segmentation into a usable template, and it is the only step with a hard, tested guarantee.

## The idea

Two tests decide whether a region is paintable:

- **Area**: is it at least `min_area` pixels?
- **Width**: can a circle of radius `min_radius` fit inside it? (If not, no brush of that size can paint it without crossing into the neighbours.)

Regions failing either test are absorbed by the most similar neighbour, smallest first.

## The maths

**Connected regions.** Each palette colour's mask is split into 4-connected components. Every component is one region (one thing to paint, one printed number).

**Inscribed-circle radius via a distance transform.** Mark every pixel that touches a pixel of a different region (horizontally or vertically), plus everything outside the image, as an *edge* pixel. Let `dt(p)` be the Euclidean distance from `p` to the nearest edge pixel. Because the nearest edge pixel to `p` always belongs to the border of `p`'s own region, one transform for the whole image gives every region's distance map at once. For region `R`:

```
radius(R)  = max_{p ∈ R} dt(p)  +  0.5            ( +0.5 because edge pixels are marked on both sides of a boundary )
pole(R)    = argmax_{p ∈ R} dt(p)                  ( the "centre" of the largest inscribed circle )
area(R)    = number of pixels in R
```

A region is **bad** if `area(R) < min_area` or `radius(R) < min_radius`.

**Merge cost.** A bad region `R` with current colour `c_R` considers each neighbouring region `Q` with colour `c_Q ≠ c_R`:

```
cost(R → Q) = ‖ c_R − c_Q ‖ · ( 1.5 − share(R, Q) )

share(R, Q) = (length of the shared boundary R–Q) / (total boundary length of R)  ∈ (0, 1]
```

`‖·‖` is the Lab distance between *palette colours*. The factor `(1.5 − share)` gently prefers a neighbour that surrounds the region (large share) over one it only touches at a corner. `R` takes the colour of the cheapest `Q`.

## The algorithm

```
Algorithm 6  Region cleanup  (clean_regions)
Input : label map l, palette colours c, min_area, min_radius, max_passes = 30
Output: label map in which every connected region passes both tests

 1  repeat up to max_passes times
 2      split every colour into 4-connected regions ; compute area, radius for each     (distance transform)
 3      B ← regions with area < min_area or radius < min_radius
 4      if B is empty: stop
 5      build the region adjacency with shared-boundary lengths
 6      for R in B ordered by increasing area:
 7          if R has no neighbour of a different colour: continue
 8          Q* ← argmin over neighbours Q (colour ≠ R's current colour) of cost(R → Q)
 9          give R the colour of Q*                           (updated immediately, so later decisions see it)
10      if nothing changed: stop
11  return l
```

Processing smallest first and updating colours immediately means chains of tiny regions collapse into their surroundings in one pass; regions that are no longer a separate colour from their neighbour simply fuse when the next pass recomputes the components.

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `min_area` | **Min region area** · `--min-area` · `min_area` | 120 (low) · 70 (medium) · 40 (high) px | Smallest allowed region |
| `min_radius` | **Min region radius** · `--min-radius` · `min_radius` | 4.0 · 3.0 · 2.5 px | Narrowest allowed region (radius of the largest circle that fits) |
| `max_passes` | `clean_regions(max_passes=...)` | 30 | Safety cap on iterations |

### Turning pixels into real units

The limits are in *working-resolution* pixels (the image is resized so its long side is at most **Working resolution**). Your canvas's physical size converts them:

```
mm_per_pixel   = canvas long side (mm) / working size (px)
brush radius   = min_radius × mm_per_pixel
min region area = min_area × mm_per_pixel²
```

Example: a 40 × 50 cm canvas (long side 500 mm) at 800 px: `mm_per_pixel = 0.625`.

| Preset | Working size | `mm_per_pixel` | min radius in mm | min area |
|---|---|---|---|---|
| low | 800 | 0.625 | 2.5 mm (a 5 mm-wide stroke) | ≈ 47 mm² (about 7 × 7 mm) |
| medium | 1200 | 0.417 | 1.25 mm | ≈ 12 mm² |
| high | 1600 | 0.313 | 0.78 mm (a very fine brush) | ≈ 4 mm² |

If your painting is smaller, or your brush bigger, raise `min_radius` and `min_area` or lower the working resolution.

## Guarantees and limits

- Both tests hold for every connected region after cleanup; the pipeline tests assert it for both methods on synthetic data (`tests/test_pipeline.py::test_regions_are_paintable`).
- There is no formal proof of termination for all inputs, hence the pass cap; in practice it converges within a handful of passes.
- Cleanup only *recolours* regions, never moves boundaries, so each boundary stays where the labelling stage put it.
- It can delete a colour entirely (every region of that colour absorbed); `finalize` then drops it, so the final palette can be smaller than `k`.

## Cost

The distance transform and component labelling are linear in the number of pixels; the merge loop is linear in the number of bad regions and their neighbours. Measured cleanup time is a fraction of a second on small photos and up to roughly 2 s at the medium and high presets.

## Code

- `pbn/backend/regions.py` → `clean_regions`, `connected_components`, `region_geometry`, `adjacency`
