# How the algorithms work

One document per algorithm used in this project. Each follows the same shape:

1. **What it does and why it is here**
2. **The idea**, in plain words
3. **The maths**
4. **The algorithm** as pseudo-code, written like the algorithm boxes in a paper
5. **Parameters**: which knobs in the app / CLI / code map onto which symbols in the maths, and what they control
6. **Cost, behaviour and what we measured**
7. **Code pointers and references**

Formulas are written in plain text inside code blocks so they read the same in any Markdown viewer.

## The whole pipeline

```
photo ──► resize ──► bilateral smoothing ──► CIELAB                       (02, 01)
                                │
          ┌─────────────────────┴──────────────────────┐
  A. kmeans-potts                                B. slic-merge
  k-means palette over pixels      (03)          SLIC superpixels                 (05)
  Potts graph-cut labelling        (04)          Ward merging to N regions        (06)
                                                 weighted k-means over regions    (03)
          └─────────────────────┬──────────────────────┘
                     region cleanup: min area / min radius                        (07)
                                │
              finalize: palette = mean colour, numbered dark → light              (03)
                                │
        boundary tracing ─► smoothing ─► number placement ─► SVG / PNG            (08)
                                │
   paint recipes:  Kubelka–Munk mixing model (09) ─► recipe search (10)
                   ─► paint quantities and the mixed-colour preview (11)
```

The header artwork of the web app (12) is generated with the same region and outline code.

## Index

| # | Document | Used for |
|---|----------|----------|
| 01 | [Colour science: CIELAB and ΔE](01-colour-science.md) | Measuring "how different do two colours look" everywhere in the project |
| 02 | [Bilateral smoothing](02-bilateral-smoothing.md) | Removing noise and texture while keeping edges, before any colour grouping |
| 03 | [k-means palette](03-kmeans-palette.md) | Choosing the N paint colours; also the palette step of method B |
| 04 | [Potts model and graph cut](04-potts-graph-cut.md) | Method A: assigning every pixel a palette colour with spatial smoothness |
| 05 | [SLIC superpixels](05-slic-superpixels.md) | Method B: cutting the image into small colour-coherent blobs |
| 06 | [Ward region merging](06-ward-region-merging.md) | Method B: merging blobs down to a target number of regions |
| 07 | [Region cleanup](07-region-cleanup.md) | Guaranteeing every region is big enough and wide enough to paint |
| 08 | [Boundary tracing and numbering](08-boundary-tracing-and-numbering.md) | Turning a label map into clean vector outlines with numbers |
| 09 | [Kubelka–Munk paint mixing](09-kubelka-munk-paint-mixing.md) | Predicting the colour of a mix of acrylic tubes |
| 10 | [Recipe search](10-recipe-search.md) | Finding the tube mix closest to each palette colour (the "optimisation") |
| 11 | [Quantities and previews](11-quantities-and-previews.md) | How much of each tube to mix, and the mixed-colour preview |
| 12 | [Header artwork](12-header-artwork.md) | The generative picture behind the app title |

## Which setting controls which algorithm

| Setting (app label · CLI flag) | Default (low / medium / high) | Algorithm it feeds | Document |
|---|---|---|---|
| Working resolution · `--size` | 800 / 1200 / 1600 px | Everything downstream (all pixel limits are in these pixels) | 07 |
| Colours · `-k`, `--colors` | 16 / 20 / 24 | k-means cluster count | 03 |
| Smoothing passes · `--smooth-iters` | 3 / 2 / 1 | Number of bilateral filter passes | 02 |
| Min region area · `--min-area` | 120 / 70 / 40 px | Cleanup threshold on area | 07 |
| Min region radius · `--min-radius` | 4.0 / 3.0 / 2.5 px | Cleanup threshold on inscribed-circle radius | 07 |
| Smoothness (λ) · `--lam` | 2.0 / 1.5 / 1.0 | Potts pairwise weight (method A) | 04 |
| Target regions · `--regions` | 300 / 800 / 1800 | Ward merging stop count (method B) | 06 |
| Initial superpixels · `--superpixels` | 4000 / 9000 / 20000 | SLIC seed count (method B) | 05 |
| SLIC compactness · `--compactness` | 0.05 | SLIC colour-vs-space weight (method B) | 05 |
| Output scale · `--scale` | 3 | Raster outline size only | 08 |
| Paint set (tube colours, on/off) | 12 standard tubes | Kubelka–Munk inputs | 09 |
| Max tubes per mix · `--max-paints` | 3 (range 2–6) | Size of the recipe search space | 10 |
| Recipe style · `--tube-penalty` | Simplest = 1.0 | Per-tube penalty λ in the recipe objective | 10 |
| Canvas size, paint per 100 cm², coats · `--canvas`, `--ml-per-100cm2`, `--coats` | 40×50 cm, 1.5 ml, 2 | Paint quantity estimate | 11 |

Everything not listed above (for example the Potts edge sensitivity or the number of recipe search starts) is a named constant in the code; the relevant document says where.

## Conventions

- **Pixels** always means *working-resolution* pixels: the image is first shrunk so its long side is at most `size`.
- **Lab** means CIELAB computed from sRGB with a D65 white point (OpenCV's conversion); L is 0–100.
- **Parts** are volume parts of paint, for example "3 parts white + 1 part blue" is 75% / 25% by volume.
- Names such as `potts_labels` or `refine` refer to functions in `pbn/backend/`.
