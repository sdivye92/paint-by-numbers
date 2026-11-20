# 05 · SLIC superpixels (method B)

## What it does and why it is here

Method B does not reason about a million pixels one by one. It first cuts the image into a few thousand small blobs called **superpixels**, each a compact patch of similar colour that respects edges. Everything after that (merging, palette choice) works on blobs, which is far cheaper and gives regions that are coherent by construction.

## The idea

SLIC (*Simple Linear Iterative Clustering*) is k-means with two changes:

1. The clustering space has **five** dimensions: the three Lab colour channels plus the pixel's `(x, y)` position. A cluster is therefore a patch that is similar in colour *and* close in space.
2. Each centre only competes for pixels in a **local window** around it, so the work is linear in the number of pixels.

A single weight, **compactness**, decides how much position matters relative to colour: high compactness gives neat grid-like squares that ignore edges; low compactness lets blobs stretch along colour edges.

## The maths

Seeds are placed on a regular grid with spacing `S = sqrt(N / K)` for `N` pixels and `K` requested superpixels. Each pixel `i` is assigned to the nearby centre `k` with the smallest

```
D(i, k) = sqrt(  d_c²  +  (m / S)² · d_s²  )

d_c = ‖ (L, a, b)_i − (L, a, b)_k ‖        colour distance (Lab, so ΔE76)
d_s = ‖ (x, y)_i − (x, y)_k ‖              spatial distance in pixels
m   = compactness
```

Dividing the spatial distance by the grid spacing `S` makes it dimensionless, so `m` is on the same scale as the colour distance (scikit-image implements the same comparison by pre-scaling the colour channels, which gives an equivalent ordering).

Only centres within a `2S × 2S` window of the pixel are considered, so each pixel is compared against at most about four centres.

**What `m` does, with numbers.** Take `S ≈ 10 px`, a spatial offset of `d_s = 15 px`, and a colour difference of `d_c = 10` (a modest ΔE):

```
m = 0.05 :  (m/S)² · d_s² = (0.005)² · 225 ≈ 0.006      →  colour term (100) dominates:  blobs follow colour edges
m = 10   :  (m/S)² · d_s² = (1.0)²   · 225 = 225        →  space term beats colour (100):  blobs become a square grid
```

This is why the right compactness here (about 0.05) looks tiny next to the value of 10 that appears in many tutorials and in scikit-image's default. The useful value depends strongly on image contrast (scikit-image itself advises searching on a log scale: 0.01, 0.1, 1, 10 …), and this project feeds SLIC an image that has *already* been smoothed by an edge-preserving filter, so colour differences inside regions are small and even a modest spatial weight overwhelms them.

## The algorithm

```
Algorithm 4  SLIC superpixels (as run by skimage.segmentation.slic on a Lab image)
Input : Lab image, K superpixels, compactness m, pre-smoothing σ = 1
Output: superpixel label map

 1  smooth the image with a Gaussian of width σ
 2  place K cluster centres C_k = (L, a, b, x, y) on a regular grid with spacing S
 3  repeat up to 10 times
 4      for every centre C_k:
 5          for every pixel i in the 2S × 2S window around C_k:
 6              if D(i, C_k) < best[i]:  best[i] ← D(i, C_k) ;  label[i] ← k
 7      for every k:  C_k ← mean of the (L, a, b, x, y) of all pixels with label k
 8  enforce connectivity: relabel orphaned fragments and merge segments smaller than
    about half the nominal size into an adjacent superpixel
 9  return label
```

The implementation is `skimage.segmentation.slic(lab, n_segments=K, compactness=m, sigma=1, convert2lab=False, start_label=0, enforce_connectivity=True, channel_axis=-1)`. The image is passed already in Lab (`convert2lab=False`) because the compactness scale above depends on it.

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `K` | **Initial superpixels** · `--superpixels` · `superpixels` | 4000 (low) · 9000 (medium) · 20000 (high); slider 500–30000 | Resolution of the blob layer (roughly 85–110 px per blob at the presets). Must be well above the target region count. The returned count is only approximately `K` |
| `m` | **SLIC compactness** · `--compactness` · `compactness` | 0.05; menu 0.01 … 0.3 | Colour-versus-space weight (see numbers above) |
| `σ` | fixed in `slic_merge` | 1 | Light pre-blur inside SLIC |
| iterations | scikit-image default | 10 | Convergence |

### What we measured

Astronaut photograph, low preset, method B (final result after merging and cleanup):

| compactness | final regions | mean ΔE from photo | what it looks like |
|---|---|---|---|
| 10 | 120 | 10.21 | Square staircase blocks; edges ignored |
| 3 | 120 | 10.21 | Same blocks |
| 1 | 126 | 10.05 | Still blocky |
| 0.3 | 122 | 8.58 | Edges followed; some blocky patches remain |
| **0.1** | 127 | **8.41** | Clean edge-following shapes |
| 0.03 | 137 | 8.98 | Keeps more fine facial detail, slightly ragged |
| 0.01 | 132 | 9.10 | Ragged |

The first version of this project used compactness 10, taken from common examples, and produced the blocky look in the first three rows. Moving to 0.05 fixed it. Lesson: the useful range depends on the contrast of the image you feed in, so tune it on your own pipeline rather than copying a value.

## Cost and behaviour

Each iteration is `O(N)`. The whole of method B (smoothing, SLIC, merging, palette, cleanup) took about 0.3–0.5 s on 500–600 px photos, 1.5 s at the medium preset and 2.3 s at the high preset on the author's laptop, versus about 2–25 s for method A on the same images.

## Why SLIC and then merge?

SLIC gives a small, edge-respecting set of building blocks. Merging them (06) lets you choose the number of regions *directly*, which is the quantity that decides how paintable the template is.

## Code and references

- `pbn/backend/methods.py` → `slic_merge` (the `slic(...)` call)
- R. Achanta et al., "SLIC superpixels compared to state-of-the-art superpixel methods", *IEEE TPAMI* 34(11), 2012.
