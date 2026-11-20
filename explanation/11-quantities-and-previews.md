# 11 · Paint quantities, mixed-colour preview and quality metrics

## What it does and why it is here

Three small but useful calculations sit on top of the recipes:

1. **How much paint** to mix for each numbered colour, and the total per tube.
2. A **mixed-colour preview**: the template repainted with the colours your recipes should actually produce.
3. **Quality metrics** that say how close each stage is to the photo.

## 1 · Paint quantities

### The maths

For palette colour `c`, with `cov_c` its share of the image area (pixels with label `c` divided by all pixels):

```
total_ml(c) = cov_c · (W · H / 100) · rate · coats · (1 + margin)
```

- `W · H` is the canvas area in cm², so `W · H / 100` is the area in units of 100 cm².
- `rate` is the paint needed per 100 cm² per coat.
- `margin` is a safety allowance (0.25).

The volume is split across the recipe's tubes in proportion to their parts:

```
ml(c, tube i) = total_ml(c) · parts_i / Σ parts
usage(tube i) = Σ_c ml(c, tube i)                        (the "Total paint needed" table)
```

### The algorithm

```
Algorithm Q1  Paint quantities, usage and mixed preview  (recipes.build_recipes, usage_summary, mix_preview_image)
Input : label map, recipes (parts per tube, predicted mix colour) for every palette colour,
        canvas W × H cm, rate (ml per 100 cm² per coat), coats, margin = 0.25
Output: ml per tube for every colour, total ml per tube, mixed-colour preview

 1  area ← W · H / 100                                              (in units of 100 cm²)
 2  for every palette colour c:
 3      cov_c ← (pixels with label c) / (all pixels)
 4      total_ml_c ← cov_c · area · rate · coats · (1 + margin)
 5      for every tube i in the recipe of c:
 6          ml(c, i) ← total_ml_c · parts_i / Σ parts
 7  for every tube i:  usage_i ← Σ_c ml(c, i)  ;  sort tubes by usage, largest first
 8  mixed_preview ← predicted_mix_colour[ label ]                   (palette lookup per pixel)
 9  return ml, usage, mixed_preview
```

### Worked example

A 40 × 50 cm canvas: `W · H = 2000 cm²`, so `20` units of 100 cm². With `rate = 1.5 ml`, `coats = 2` and `margin = 0.25`:

```
all colours together:   20 · 1.5 · 2 · 1.25 = 75 ml
a colour covering 12 %: 0.12 · 75           = 9 ml    (for example 3 parts white + 1 part ochre → 6.75 ml white + 2.25 ml ochre)
```

### Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `W`, `H` | **Canvas width / height (cm)** · `--canvas WxH` | 40 × 50 | Total paint scales with area |
| `rate` | **Paint per 100 cm² per coat (ml)** · `--ml-per-100cm2` | 1.5 (range 0.2 – 6) | Coverage. This is a rough default for medium-body acrylic; raise it for thick application, lower it for thin washes. **It is a guess, not a measurement** |
| `coats` | **Coats** · `--coats` | 2 | Number of layers (light colours over dark often need more) |
| `margin` | `build_recipes(margin=...)` | 0.25 | Allowance for waste and mixing losses (fixed) |

Quantities are *planning estimates*. Tune `rate` after your first painting.

## 2 · The mixed-colour preview

The algorithm preview paints every region with its palette colour (the k-means centre). The **mixed preview** paints every region with the colour its recipe is *predicted to mix to* (the Kubelka–Munk output from 09), so you can see how your real paints will drift from the template:

```
mixed_preview(pixel) = predicted_mix_colour( recipe[ label(pixel) ] )
```

It is a palette lookup, so it costs essentially nothing. The app shows three images side by side (the photo, the algorithm preview and the mixed preview) with fullscreen buttons, and the mixed preview can be exported as `*_mix_preview.png`.

## 3 · Quality metrics

All metrics use the Lab-space measures from 01.

| Metric | Definition | Where it appears |
|---|---|---|
| Mean colour error (`mean_dE`) | Mean over pixels of ‖Lab(photo) − Lab(preview)‖ (ΔE76) | Compare tab table; Generate tab stat; captions under the previews |
| Recipe ΔE | ΔE2000 between a palette colour and its predicted mix | Recipe table, with the label excellent (< 2) / good (< 5) / approximate |
| Colours / regions | Final palette size; number of connected regions | Stats |
| Median region area, smallest region, smallest radius | From the cleanup geometry (07) | Compare tab table |
| Time | Sum of per-stage timings | Stats |

How to read them: the *template* error (algorithm preview vs photo) reflects how much detail was lost to quantisation. The *mixed* error is that plus the paints' mismatch. On the coffee sample they were ΔE 7.1 and 8.0; on a night photograph at medium detail 9.0 and 9.3, so good recipes cost about 0.3 – 1 ΔE of fidelity.

## Exported data

- `*_recipes.csv` columns: `number, target_hex, predicted_hex, delta_e2000, match, recipe, coverage_pct, total_ml, ml_by_paint`.
- `*_recipes.png`: a printable sheet with target and predicted swatches, the recipe, ml per tube, and the paint totals.
- `*_palette.json`: palette hex values and coverage; with recipes enabled each entry also has the parts, ΔE and ml per tube.
- In the web app all selected files are bundled into one ZIP (one folder inside) with a `package_info.json` that records the method, settings, canvas and recipe settings; `run --zip` does the same from the command line.

## Code

- `pbn/backend/recipes.py` → `build_recipes`, `usage_summary`, `mix_preview_image`, `preview_error`, `recipes_csv`, `recipe_sheet_image`
- `pbn/backend/compare.py` → `metrics`
- `pbn/frontend/paints_ui.py` → `mix_comparison`
