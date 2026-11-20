# 08 · Boundary tracing and numbering

## What it does and why it is here

The label map is a grid of palette indices. A printable template needs **clean outlines** and a **number inside each region**. This stage turns the label map into vector outlines whose lines are *shared* between neighbouring regions, smooths them, and places a correctly sized number at the best spot in each region.

## The idea

Drawing each region's outline separately would put two slightly different lines on every shared boundary (double lines, gaps). Instead the boundary between two regions is traced **once**, as a path along the pixel edges where the labels change, cut at the points where three or more regions meet ("junctions"). Each path is then smoothed to remove the pixel staircase and simplified to a few points.

## Part 1 · Tracing the boundaries

Work on the **pixel-corner grid**: a point `(x, y)` is the corner between four pixels, with `(W+1) × (H+1)` corners. A *boundary edge* is a unit segment between two corners that separates two pixels with different labels. The image border counts as a boundary (pixels outside have label −1).

Build a graph whose nodes are corners and whose edges are boundary edges. Each corner has at most 4 neighbours.

- degree 2: the boundary simply continues
- degree 3 or 4: a **junction** where regions meet
- the four image corners are also treated as junctions so the page outline stays rectangular

```
Algorithm 7  Boundary chain tracing  (trace_chains)
Input : label map l
Output: list of smoothed polylines (chains), each marked open or closed

 1  mark every unit edge between differently-labelled pixels (and along the image border)
 2  build the corner graph ; deg(v) ← number of marked edges at corner v
 3  stop(v) ← ( deg(v) ≠ 2 ) or v is an image corner
 4  for every corner v with stop(v) and every unused edge e at v:
 5      walk from v along e, always continuing through degree-2 corners,
 6      until reaching another stop corner (or returning to v) ;  mark the edges used ;  record the chain
 7  for every remaining unused edge:                     (boundaries with no junction, e.g. an island)
 8      walk until returning to the start ;  record a closed chain
 9  for every chain:
10      if closed:  smooth with wrap-around
11      else:       smooth with the two end points fixed
12      simplify with Douglas–Peucker
13  return chains
```

Each boundary edge is used exactly once, so every shared boundary appears once in the output.

## Part 2 · Smoothing the chains

A traced chain is a staircase of unit steps. Replace each point by a Gaussian-weighted average of the points around it **along the chain**:

```
p'_i = Σ_j g(j) · p_{i+j},      g(j) ∝ exp( − j² / (2σ²) ),     σ = 2 samples
```

Each step along the chain is about one pixel, so `σ = 2` smooths over a few pixels of boundary: staircases become diagonals and curves, while sharp corners are rounded by roughly the same amount. For **open** chains the end points are restored afterwards, which pins every junction so neighbouring chains still meet exactly. For **closed** chains the average wraps around. Image-corner points are pinned too, so the page border stays square.

## Part 3 · Simplifying: Douglas–Peucker

Smoothed chains have far more points than needed. The Douglas–Peucker algorithm keeps only the points that matter within a tolerance `ε`:

```
Algorithm 8  Douglas–Peucker simplification  (cv2.approxPolyDP)
Input : polyline P = (p_0 … p_n), tolerance ε
Output: simplified polyline

 1  find the point p_k farthest from the line through p_0 and p_n ; let d be its distance
 2  if d > ε:  return  DP(p_0 … p_k)  followed by  DP(p_k … p_n)  (without repeating p_k)
 3  else:      return  ( p_0, p_n )
```

`ε = 0.6` pixels by default: invisible at print size but cuts the file to a fraction of its size. The result is written as SVG `<path>` elements and, for the PNG, drawn with anti-aliased polylines at `scale ×` resolution (sub-pixel positions kept with fixed-point coordinates).

## Part 4 · Placing the numbers

Each region needs a number where the digits fit. The same distance transform used by cleanup (07) gives, for every region, the largest inscribed circle: its centre is the **pole of inaccessibility** (`argmax` of the distance transform) and its radius is `r`.

**Fitting the text.** Let the digits at nominal size have width `w₁` and height `h₁` (measured with OpenCV's font metrics). The text box must sit inside the circle, so its half-diagonal must be at most `0.9 r`:

```
scale   s = 0.9 · r / ( 0.5 · sqrt(w₁² + h₁²) )
digit height  h = min( s · h₁ ,  max_digit_h )          max_digit_h = 8 working pixels
```

Big regions therefore get uniformly sized numbers (capped at 8 px), and small regions get proportionally small numbers. Numbers that would be too small are omitted: below 4 output pixels in the PNG (after scaling) and below 1.3 working pixels in the SVG. In the SVG, the font size is `h / 0.72`, because a digit's height is about 0.72 of the font's em size.

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `σ` | `trace_chains(sigma=...)` | 2.0 | Smoothness of outlines; larger rounds corners more |
| `ε` | `trace_chains(eps=...)` | 0.6 px | Simplification tolerance (path size vs fidelity) |
| output scale | **Output scale** in the app · `--scale` | 3 (range 1–4) | Size multiplier of the outline PNG and the SVG's display size. The SVG itself stays vector |
| `max_digit_h` | `outline_image` / `svg_document` | 8 working px | Largest number height |
| line width | fixed | 1 px (PNG), 0.35 units (SVG) | Stroke weight |

`σ`, `ε` and the digit constants are fixed in code, not exposed in the interface.

## Cost and behaviour

Tracing is linear in the number of boundary edges (it grows with total boundary length, so with detail) and walks the corner graph in plain Python over integer arrays. It was not benchmarked separately; in practice it is a small part of the total time next to the labelling stage.

## Code and references

- `pbn/backend/render.py` → `trace_chains`, `region_table`, `fit_text`, `outline_image`, `svg_document`
- D. Douglas, T. Peucker, "Algorithms for the reduction of the number of points required to represent a digitized line", *Cartographica* 10(2), 1973.
- V. Agafonkin, *polylabel* (the "pole of inaccessibility"); here approximated by the distance-transform maximum, which is exact on the pixel grid.
