# Paint by Numbers

Turn any photograph into a **paint-by-numbers template**: a numbered outline you can print, a colour legend, and, for acrylic painters, a **mixing recipe for every numbered colour** from a standard 12-tube set, with quantities.

You get a web app (Streamlit) and a command-line tool, backed by two interchangeable segmentation pipelines, a small graph-cut solver, and a pigment-mixing model. Every algorithm is explained, with the maths and pseudo-code, in [`explanation/`](explanation/README.md).

## Contents

- [Quick start](#quick-start)
- [How it works at a glance](#how-it-works-at-a-glance)
- [The web app](#the-web-app)
- [Command line](#command-line)
- [Choosing a method](#choosing-a-method)
- [Detail presets](#detail-presets)
- [Settings reference](#settings-reference)
- [Acrylic paint recipes](#acrylic-paint-recipes)
- [Output files](#output-files)
- [Project layout](#project-layout)
- [Performance](#performance)
- [Tests](#tests)
- [Design notes and findings](#design-notes-and-findings)
- [Limitations and ideas](#limitations-and-ideas)
- [Troubleshooting](#troubleshooting)
- [Documentation index](#documentation-index)

## Quick start

Python 3.12 is the tested version. [uv](https://docs.astral.sh/uv/) is the simplest way to set up:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

Start the web app (opens on http://localhost:8501):

```bash
.venv/bin/python -m pbn app
```

Or convert one photo from the terminal:

```bash
.venv/bin/python -m pbn run samples/coffee.jpg --detail medium --recipes -o out
```

Run the tests:

```bash
.venv/bin/python -m pytest
```

> Run commands from the project folder: the app reads its theme from `.streamlit/config.toml` there.

## How it works at a glance

```
photo ─► resize ─► bilateral smoothing ─► CIELAB
                               │
        ┌──────────────────────┴───────────────────────┐
 A. kmeans-potts                                 B. slic-merge
 k-means palette over pixels                     SLIC superpixels
 Potts graph-cut labelling                       Ward merging to N regions
                                                 weighted k-means over regions
        └──────────────────────┬───────────────────────┘
                 region cleanup (min area, min radius)
                               │
            palette = mean colour, numbered dark → light
                               │
       boundary tracing ─► smoothing ─► numbers ─► SVG / PNG
                               │
   Kubelka–Munk mixing model ─► recipe search ─► quantities ─► mixed preview
```

1. **Smooth** the photo with an edge-preserving filter so noise doesn't become thousands of specks.
2. **Group colours** with one of two methods (below), always in CIELAB so "close" means "looks similar".
3. **Clean up** so every region is large and wide enough for a brush; this step has a tested guarantee.
4. **Trace** shared, smoothed outlines (vector, no double lines) and place a number at the centre of each region.
5. **Mix**: predict paint mixes with a pigment model and search for the closest recipe for each colour.

## The web app

```bash
.venv/bin/python -m pbn app            # same as: .venv/bin/streamlit run pbn/frontend/app.py
.venv/bin/python -m pbn app --port 8600
```

Choose a photo in the sidebar (upload one or use a sample), then use either tab. Results stay on screen until you run again, and identical runs are cached.

**Compare methods**: runs both pipelines on the same image with the same settings and shows, side by side: the original, a metrics table (regions, colour error, time…), both colour previews, and both numbered outlines.

**Generate & export**: pick a method and every parameter (a *Detail preset* fills sensible starting values), press **Generate**, then:

- see the colour preview, numbered outline and legend (hover any image for a fullscreen button);
- under **Paint recipes**: edit your paint set, set canvas size and coverage, choose *Max tubes per mix* (2–6) and *Recipe style*, and read the recipe table and total paint needed;
- under **Photo vs template vs your paints**: compare the photo, the algorithm's palette, and the template repainted in the colours your mixes should produce;
- under **Download**: choose which artifacts to include and a package name, then press **Download ZIP**. The ZIP is built at the moment you click and goes to your browser as an ordinary download, so it lands on *your* computer, never on the server. Your browser decides the folder (most can be set to "ask where to save each file").

The ZIP contains one folder with your files plus a `package_info.json` recording the method, settings and recipe settings used. Nothing is prepared in advance and nothing is kept: each click renders the files in a temporary folder on the server, streams the ZIP to that visitor, and discards the folder. This also means a deployed copy of the app never stores anyone's files.

## Command line

```bash
.venv/bin/python -m pbn run IMAGE [options]         # one image, one method
.venv/bin/python -m pbn compare IMAGE... [options]  # both methods + a side-by-side sheet
.venv/bin/python -m pbn app [--port N]              # the web app
```

Examples:

```bash
.venv/bin/python -m pbn run photo.jpg -m kmeans-potts --detail medium -o out
.venv/bin/python -m pbn run photo.jpg --recipes --canvas 40x50 --max-paints 4 --tube-penalty 0.25 -o out
.venv/bin/python -m pbn compare samples/*.jpg --detail high -o out
```

| Option | Commands | Meaning |
|---|---|---|
| `-o, --out DIR` | run, compare | Output folder (default `out`) |
| `-m, --method` | run | `kmeans-potts` (default) or `slic-merge` |
| `--detail low\|medium\|high` | run, compare | Preset for the settings below; any explicit flag overrides it |
| `-k, --colors N` | run, compare | Palette size |
| `--size PX` | run, compare | Working resolution (long side) |
| `--min-area N`, `--min-radius R` | run, compare | Paintability limits (working pixels) |
| `--smooth-iters N` | run, compare | Smoothing passes (0 = none) |
| `--lam X` | run, compare | Smoothness (method A) |
| `--regions N`, `--superpixels N`, `--compactness X` | run, compare | Method B controls |
| `--scale N` | run, compare | Outline PNG scale (default 3) |
| `--recipes` | run | Also write paint recipes (PNG sheet, CSV, mixed preview) |
| `--zip` | run | Also bundle everything into `<name>.zip` (with `package_info.json`) |
| `--canvas WxH` | run | Canvas size in cm for quantities (default `40x50`) |
| `--max-paints 2…6` | run | Maximum tubes per mix (default 3) |
| `--tube-penalty X` | run | Cost per extra tube: 1.0 simple (default) … 0.1 most accurate |
| `--ml-per-100cm2 X`, `--coats N` | run | Coverage estimate (defaults 1.5 ml, 2 coats) |

## Choosing a method

|  | `kmeans-potts` (A) | `slic-merge` (B) |
|---|---|---|
| Idea | Pick a palette by k-means, then label every pixel with a **graph cut** that trades colour fit against spatial smoothness | Cut the image into **superpixels**, merge them down to a chosen region count, then pick the palette over the regions |
| Palette | k-means++ in CIELAB over pixels | Weighted k-means over region mean colours |
| Controls | `--lam` (smoothness) | `--regions`, `--superpixels`, `--compactness` |
| Strengths | Smooth, edge-following shapes; very good colour fit | Direct control of region count; much faster |
| Typical time | 2–25 s | 0.3–2.5 s |
| Details | [04](explanation/04-potts-graph-cut.md) | [05](explanation/05-slic-superpixels.md), [06](explanation/06-ward-region-merging.md) |

On the sample photos the two are close in quality (within about 0.5 mean ΔE of each other). Method A is slightly smoother along edges; method B is several times faster. Use the *Compare methods* tab on your own photo.

## Detail presets

`--detail low|medium|high` (and the app's preset menu) sets resolution, palette size, smoothing and the paintability limits together. Anything you set explicitly overrides the preset.

| | Working size | Colours | Min area / radius | Smoothing | λ | Target regions | Superpixels |
|---|---|---|---|---|---|---|---|
| **low** (default) | 800 | 16 | 120 / 4.0 | 3 | 2.0 | 300 | 4000 |
| **medium** | 1200 | 20 | 70 / 3.0 | 2 | 1.5 | 800 | 9000 |
| **high** | 1600 | 24 | 40 / 2.5 | 1 | 1.0 | 1800 | 20000 |

Final regions on a night photograph (method A): 202 at low, 473 at medium, 1276 at high. More detail means many more, smaller regions, so print the SVG large. At `high` the raster outline's numbers become tiny; the SVG stays crisp.

The pixel limits are in working pixels. Convert them to your canvas: on a 40 × 50 cm canvas at 800 px, a minimum radius of 4 px is 2.5 mm; at 1600 px, 2.5 px is 0.78 mm, which needs a very fine brush ([07](explanation/07-region-cleanup.md)).

## Settings reference

| Setting (app · CLI) | What it controls | Algorithm |
|---|---|---|
| Working resolution · `--size` | Processing resolution; all pixel limits are in these pixels | all |
| Colours · `-k` | Palette size (the final count can be lower if a colour ends up unused) | [03](explanation/03-kmeans-palette.md) |
| Smoothing passes · `--smooth-iters` | How flat regions become before grouping; 1–2 keep detail, 3 is chunky, 0 can look blocky | [02](explanation/02-bilateral-smoothing.md) |
| Smoothness (λ) · `--lam` | Method A: higher = blobbier regions, fewer specks | [04](explanation/04-potts-graph-cut.md) |
| Target regions · `--regions` | Method B: ceiling on the region count before colours are assigned | [06](explanation/06-ward-region-merging.md) |
| Initial superpixels · `--superpixels` | Method B: resolution of the first blob layer | [05](explanation/05-slic-superpixels.md) |
| SLIC compactness · `--compactness` | Method B: colour-vs-position weight; ≥ 1 collapses to a grid on smoothed images | [05](explanation/05-slic-superpixels.md) |
| Min region area / radius | Smallest allowed region and narrowest allowed width | [07](explanation/07-region-cleanup.md) |
| Output scale · `--scale` | Outline PNG size (SVG is vector) | [08](explanation/08-boundary-tracing-and-numbering.md) |
| Paint set | Which tubes, and their colours | [09](explanation/09-kubelka-munk-paint-mixing.md) |
| Max tubes per mix · `--max-paints` | Cap on tubes in one recipe (2–6) | [10](explanation/10-recipe-search.md) |
| Recipe style · `--tube-penalty` | Simplest 1.0 · Balanced 0.5 · Accurate 0.25 · Most accurate 0.1 | [10](explanation/10-recipe-search.md) |
| Canvas, paint per 100 cm², coats | Paint quantities | [11](explanation/11-quantities-and-previews.md) |

## Acrylic paint recipes

For every numbered colour the app finds the closest mix from a standard 12-tube acrylic set (titanium white, mars black, cadmium yellow light and medium, yellow ochre, cadmium red, alizarin crimson, ultramarine, phthalo blue, phthalo green, burnt sienna, burnt umber), written as volume ratios such as *16 parts Titanium White + 3 parts Burnt Sienna + 1 part Yellow Ochre*. It also estimates how much of each tube to mix for your canvas and shows the total paint needed.

### The mixing model

A small **Kubelka–Munk** model predicts the colour of a mix from each tube's on-screen colour and a relative opacity. It captures subtractive behaviour (yellow + blue goes green, tints lighten, strong tinters like phthalos go a long way). It is a coarse, three-band approximation: pigments vary by brand and batch, so **tube colours are editable** in the app. Paint a thick swatch of each tube and set its colour for better matches. See [09](explanation/09-kubelka-munk-paint-mixing.md).

### How recipes are found (the optimisation)

Each palette colour is matched independently by a **discrete optimisation**. There is *no* gradient descent, genetic algorithm or least squares: parts of paint are whole numbers, and the search space is small enough for the two methods below.

**Variables.** For each enabled tube an integer number of parts from `0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48` (0 = unused), with at most *m* tubes non-zero (*m* = Max tubes per mix).

**Objective** (minimised per colour):

```
J(p) = ΔE2000( target, predicted colour of mix p )  +  λ · (tubes used − 1)  +  0.3 · log2( total parts )
```

The first term is colour error; the others favour fewer tubes and smaller ratios. *λ* is the **Recipe style** (Simplest 1.0 … Most accurate 0.1).

**Method.**

- **Up to 4 tubes: exhaustive search.** Every recipe in reduced integer ratios (2,058 for ≤ 2 tubes, 121,078 for ≤ 3, 603,703 for ≤ 4, with 12 tubes) is predicted once and cached. For each target, a k-d tree finds the 128 nearest predicted colours, which are re-ranked by *J*. Within the allowed ratios this is essentially the optimum.
- **5–6 tubes: local search.** Too many recipes to list, so steepest-descent hill climbing starts from the 6 best library recipes and repeatedly takes the best single move (one tube up or down a ratio step, add a tube, drop a tube, swap a tube) until nothing improves. It keeps the best result, so it is never worse than the 4-tube answer, but it can stop at a local optimum.

Full details, a worked example and measurements are in [10](explanation/10-recipe-search.md).

**What this means in practice** (measured on three sample photos): going from 2 to 3 tubes helps a lot; from 3 to 4 almost nothing at the default style; and 5–6 tubes were almost never chosen. The setting that matters is the per-tube penalty: lowering it from 1.0 to 0.25 cut the cat photo's mean ΔE from 1.36 to 0.81, mostly with 4-tube recipes.

### Quantities and previews

```
ml for a colour = share of canvas × canvas area/100 cm² × ml per 100 cm² per coat × coats × 1.25
```

The default of 1.5 ml per 100 cm² per coat is a rough guess for medium-body acrylic; tune it to your style. Three images are shown side by side: the photo, the template with its algorithm palette, and the template repainted in the *predicted mixed colours* ([11](explanation/11-quantities-and-previews.md)).

### Limits to keep in mind

- Predictions come from a model, not a spectrophotometer. **Always mix a small swatch of the important colours first.**
- Very saturated or bright colours can fall outside what these tubes mix. They are returned as the closest achievable and marked *approximate* (ΔE ≥ 5).
- Darks and strong tinters (phthalos) are the least reliable; acrylics also dry slightly darker.
- The finest tint allowed is 1 part in 48. A very pale colour needing about 1 : 200 will be flagged approximate.

## Output files

Per image and method:

| File | Contents |
|---|---|
| `*_preview.png` | The image repainted with the palette colours |
| `*_outline.png` | Numbered outline, raster |
| `*_outline.svg` | Numbered outline, vector, with boundaries shared between neighbours (no double lines) |
| `*_legend.png` | Colour swatches with numbers, hex values and coverage |
| `*_palette.json` | Palette, coverage and region count (plus recipes and ml per tube when recipes are enabled) |
| `*_recipes.png` | Printable recipe sheet: target and mixed swatches, recipe, ml per tube, totals |
| `*_recipes.csv` | The recipe table as data |
| `*_mix_preview.png` | The template repainted in the predicted mixed colours |

The app bundles any subset you choose into a single `<name>.zip` (one folder inside, plus `package_info.json` listing the settings used); the three recipe files appear once recipes exist (CLI: `--recipes`, and `--zip` for the ZIP). `compare` also writes `compare_<image>.png`, a side-by-side sheet.

## Project layout

```
pbn/
  __main__.py          python -m pbn → CLI
  backend/             no UI dependencies; everything the CLI and app share
    cli.py             run / compare / app commands
    package.py         ZIP packaging (the app's download and `run --zip`)
    presets.py         detail presets and the parameter mapping
    imageops.py        loading, bilateral smoothing, CIELAB conversion
    methods.py         method A and B pipelines, k-means palette, Ward merging
    potts.py           Potts energy and graph-cut α-expansion
    regions.py         connected components, geometry, adjacency, cleanup
    result.py          Result container and finalize (palette from pixels, dark → light)
    render.py          boundary tracing, numbers, SVG/PNG, legend, exports
    paints.py          paint-mixing model and recipe search
    recipes.py         recipes, quantities, mixed preview, CSV and sheet
    compare.py         metrics and side-by-side sheets
  frontend/            Streamlit app
    app.py             page, tabs, export
    params.py          parameter widgets
    paints_ui.py       paint set, recipes, three-way comparison
    views.py           cached pipeline runs
    hero.py            generated header artwork
    style.py           tab typography
explanation/           one document per algorithm: maths, parameters, pseudo-code
tests/                 27 tests
samples/               three example photos (from scikit-image's data set)
.streamlit/config.toml app theme (warm paper and ink, serif headings, light and dark)
requirements.txt
out/                   generated output (safe to delete)
```

## Performance

Measured on the author's laptop; yours will differ. Method A's cost grows with pixels × colours; method B is far cheaper.

| Image (working size) | Colours | Method A | Method B |
|---|---|---|---|
| 600 × 400 | 16 | 2.3 s | 0.4 s |
| 512 × 512 | 16 | 2.7 s | 0.5 s |
| 1200 × 800 (medium) | 20 | 10 s | 1.5 s |
| 1600 × 1060 (high) | 24 | 23.5 s | 2.3 s |

The recipe library builds in 0.1–0.3 s per paint set and recipes for 16 colours take well under 0.1 s afterwards.

## Tests

```bash
.venv/bin/python -m pytest        # 27 tests, about 5 seconds
```

They check, among other things: the graph-cut move against brute force on tiny grids; that cleanup leaves no region smaller or narrower than the limits (both methods); that palette numbers run dark to light; the mixing model's qualitative behaviour (yellow + blue goes green, tints lighten); that each tube matches itself; that quantities add up; that the 5–6 tube search is never worse than 4 under the same objective; ZIP packaging (contents, safe names, no path escape, planned file names match the built archive); and a headless run of the whole web app (compare, generate, recipes, and the download button).

## Design notes and findings

Things learned while building this that are not obvious from the code:

- **SLIC compactness is tied to image contrast.** The common value of 10 turned the output into a square grid on the (pre-smoothed) images used here; 0.03–0.1 follows edges ([05](explanation/05-slic-superpixels.md)).
- **Smoothing: 1–2 passes work best for detail.** With 0 passes JPEG block artefacts and noise show up as structure and the boundaries look blocky; at 4 the lamp starbursts and window frames are gone ([02](explanation/02-bilateral-smoothing.md)).
- **The tube-count cap mattered less than the per-tube penalty.** More tubes only help when each clearly improves the match ([10](explanation/10-recipe-search.md)).
- **A pale colour can be hard for the "wrong" reason.** A very light grey needs a ~0.5% dark tint, a ratio problem rather than a tube-count problem.
- **The Potts step shortens cleanup's work.** It removes most speckle and ragged boundaries before regions are tested for size ([04](explanation/04-potts-graph-cut.md)).
- **Shared boundaries beat per-region outlines.** Tracing every boundary once gives clean vector output with no gaps or double lines ([08](explanation/08-boundary-tracing-and-numbering.md)).

## Limitations and ideas

Known limits:

- Images smaller than the working size are not upscaled, so the pixel limits then correspond to physically larger features.
- Regions are matched to recipes independently; two similar colours may get unrelated recipes.
- The paint model is approximate and has fixed per-tube opacity values (editable only in code).
- No layering or glazing model; no gloss or drying shift.
- Tints finer than 1 : 48 are not offered.

Ideas that would help:

- A calibration step: photograph swatches of your own tubes and fit their colours automatically.
- Constrain the palette to colours your tubes can mix well *before* segmentation.
- Recipe consistency across colours (prefer reusing the same few tubes).
- Finer tints ("a toothpick of black") and a guided mixing UI.
- Upscaling small inputs, and saliency-aware detail (more regions on faces).

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `ImportError: cannot import name …` in the browser after updating the code | The running server holds old cached modules. Stop it and start `python -m pbn app` again |
| Theme, header art or tab sizes didn't change | The theme is read at start-up; restart the app, and run it from the project folder |
| "Port 8501 is not available" | Another app is using it: `python -m pbn app --port 8600` |
| The ZIP downloads without asking where to save it | Browsers decide that, not the app. Turn on your browser's "ask where to save each file" setting (Chrome: Settings → Downloads; Firefox: Settings → General → Downloads) |
| Very slow at high detail | Expected for method A (it scales with pixels × colours). Use `slic-merge`, or lower the working resolution or the colour count |
| Fewer colours than I asked for | A colour that ends up unused (cleanup absorbed all its regions) is dropped; raise `-k` or lower the minimum area |
| Many recipes marked "approximate" | The colour is outside what the enabled tubes mix well. Enable more tubes, lower the *Recipe style* penalty, or raise *Max tubes* |
| Sidebar hidden | Narrow window; click the arrow at the top left |
| `pip install` fails for PyMaxflow on a very new Python | Use Python 3.12 (`uv venv --python 3.12 .venv`) |

## Documentation index

The [`explanation/`](explanation/README.md) folder has one document per algorithm, each with the idea, the maths, pseudo-code, how this project's settings map onto it, and what we measured:

1. [Colour science: CIELAB and ΔE](explanation/01-colour-science.md)
2. [Bilateral smoothing](explanation/02-bilateral-smoothing.md)
3. [k-means palette](explanation/03-kmeans-palette.md)
4. [Potts model and graph cut](explanation/04-potts-graph-cut.md)
5. [SLIC superpixels](explanation/05-slic-superpixels.md)
6. [Ward region merging](explanation/06-ward-region-merging.md)
7. [Region cleanup](explanation/07-region-cleanup.md)
8. [Boundary tracing and numbering](explanation/08-boundary-tracing-and-numbering.md)
9. [Kubelka–Munk paint mixing](explanation/09-kubelka-munk-paint-mixing.md)
10. [Recipe search](explanation/10-recipe-search.md)
11. [Quantities and previews](explanation/11-quantities-and-previews.md)
12. [Header artwork](explanation/12-header-artwork.md)

## Credits

Sample photographs come from scikit-image's bundled data set (see its documentation for their licences). Built on NumPy, SciPy, scikit-image, scikit-learn, OpenCV, PyMaxflow, Pillow and Streamlit.
