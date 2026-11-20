# 12 · Header artwork (generative)

## What it does and why it is here

The picture behind the app title is not a stock illustration: it is **generated** by a short script that reuses the project's own region and outline code. It shows a stylised dusk landscape drawn as a numbered template, with a few regions already "painted" in muted tube colours. The point is for the header to show the same thing the app produces.

## The idea

1. Make a smooth random "height" field that is roughly *how far down the page you are* plus gentle waves and a few pockets.
2. **Quantise it into bands** of equal area. This yields nested, flowing regions like the horizon bands in a sunset.
3. Treat the result as a label map and run it through the same cleanup, outline tracing and number placement as a real photo.
4. Fill about a third of the regions with paint colours and fade the whole picture in from the right so the title stays clean.

## The maths

**Field.** On a `360 × 60` grid with `x, y ∈ [0, 1]`:

```
f(x, y) = 0.85 · y
        + Σ_{(a, ν) ∈ {(0.10, 1.1), (0.06, 2.6), (0.035, 5.0), (0.02, 9.0)}}  a · sin( 2π (ν·x + φ + s·y) )
        + Σ_{pockets j}  A_j · exp( − ((x − cx_j)/sx_j)² − ((y − cy_j)/sy_j)² )
```

- `φ` and `s` are random phases and slants (from a seeded generator, so the artwork is the same every run).
- The seven Gaussian *pockets* (`A_j` of either sign) create closed islands such as a sun or a reflection.

**Equal-area bands.** With `B = 11` bands, take the quantiles of `f` at `1/B, 2/B, …` and give each pixel the index of the interval it falls in. Every band then covers the same area, whatever the field looks like.

**Reuse of the real pipeline.**

- `clean_regions` (07) removes tiny and thin pieces (`min_area = 14`, `min_radius = 2.0` grid cells, with a proxy palette that only encodes band order).
- `trace_chains` (08) produces the shared, smoothed outlines.
- `region_table` and `fit_text` (08) place the numbers (up to 10.5 units tall, omitted below 3.2).

**Painted fills.** Regions with area ≥ 40 cells are filled with probability 0.3. To get smooth fills that match the smoothed outlines, each painted region's mask is upsampled 4×, its contour found with `cv2.findContours`, smoothed with a Gaussian of σ = 7 samples (wrap-around), and simplified with Douglas–Peucker (ε = 0.7 samples). Holes are kept (`fill-rule: evenodd`). Fill colour comes from the band index, from night-blue at the top through dusk violet and rose to ochre and umber at the bottom.

**Fade.** An SVG mask with a horizontal gradient of opacities `0, 0.06, 0.4, 0.9, 1` at `0, 22, 45, 72, 100 %` of the width.

## The algorithm

```
Algorithm 13  Header artwork  (frontend/hero.py)
Input : seed, grid 360×60, bands B = 11
Output: SVG image

 1  f ← smooth field (formula above)
 2  labels ← band index of f by equal-area quantiles
 3  labels ← clean_regions(labels, min_area = 14, min_radius = 2.0)
 4  regions ← connected components of labels ;  table ← area, label, pole, radius per region
 5  painted ← { regions with area ≥ 40 chosen with probability 0.3 }
 6  for each painted region: outline ← smoothed contour of its 4×-upsampled mask ; fill with its band colour
 7  chains ← trace_chains(labels) ; draw as thin strokes
 8  for each region: place its number at the pole if it fits
 9  apply the fade mask and return the SVG
```

## Parameters

| What | Where | Value | Effect |
|---|---|---|---|
| `seed` | `hero_svg(seed=...)` | 11 | Which landscape |
| bands | `BANDS` | 11 | Number of regions across the picture |
| field terms and pockets | `_field` | see above | Shape of the bands and islands |
| painted probability | `hero_svg` | 0.3 | How "finished" the painting looks |
| colours | `BAND_COLOURS`, `INK` | muted mid-tones | Chosen to read on both the light and dark theme |
| canvas | `W, H` / `GW, GH` | 1200 × 200 units / 360 × 60 cells | Aspect ratio and detail |

The SVG is about 16 KB, is generated in well under a second, is cached for the life of the process, and is embedded in the page as a base64 background image so no extra file or network request is needed.

## Code

- `pbn/frontend/hero.py` → `hero_svg`, `hero_html`; `pbn/frontend/style.py` (tab typography)
