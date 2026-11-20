# 02 · Bilateral smoothing

## What it does and why it is here

Before colours are grouped, the photo is smoothed with an **edge-preserving filter** (`imageops.smooth`). It flattens noise, film grain, JPEG block artefacts and fine texture *inside* areas of similar colour while leaving real edges (a cheek against a background, a roofline against the sky) sharp.

Without it, grouping works on every individual pixel, and noise turns into thousands of one-pixel regions that nobody could paint. With too much of it, small real details (lamp starbursts, window frames) melt away.

## The idea

A normal blur (Gaussian) replaces each pixel by a weighted average of its neighbours, weighting only by *distance*, so it blurs across edges. A **bilateral** filter multiplies in a second weight based on *colour similarity*: a neighbour on the other side of an edge looks very different, gets a tiny weight, and barely contributes. Averaging therefore happens only among pixels that already look alike.

## The maths

For an image `I` and pixel `p`:

```
BF(I)(p) = (1 / Wp) · Σ_{q ∈ N(p)}  Gs(‖p − q‖) · Gr(‖I(p) − I(q)‖) · I(q)

Wp = Σ_{q ∈ N(p)}  Gs(‖p − q‖) · Gr(‖I(p) − I(q)‖)          (normaliser)

G_σ(x) = exp( − x² / (2σ²) )
```

- `Gs` is the **spatial** weight (nearby pixels count more), width `σs`.
- `Gr` is the **range** weight (similar colours count more), width `σr`. OpenCV's implementation for 3-channel images measures the colour distance as the **sum of absolute channel differences** on the stored 8-bit RGB values, `|ΔR| + |ΔG| + |ΔB|` (an L1 distance), rather than the Euclidean norm written above.
- `N(p)` is the neighbourhood of diameter `d` (in OpenCV, a disc of radius `d/2`).

Effect of the range weight with `σr = 35`:

```
colour distance (|ΔR|+|ΔG|+|ΔB|)   Gr
   0                               1.00
  35                               0.61
  70                               0.14
 105                               0.011
```

so a neighbour whose summed channel difference is 100 or more (a real edge) contributes about 1% or less, while neighbours within ~35 (the same surface) are averaged freely. Because the distance sums three channels, `σr = 35` is stricter than it sounds: a grey step of just 12 levels per channel already counts as 36.

Applying the filter repeatedly (**iterated bilateral filtering**) progressively flattens regions of similar colour into plateaus separated by edges, giving the "cartoon" look that suits paint-by-numbers. This behaves much like anisotropic diffusion.

## The algorithm

```
Algorithm 1  Iterated bilateral smoothing
Input : RGB image I (8-bit), passes n, d = 9, σr = 35, σs = 7
Output: smoothed image J

 1  J ← I
 2  repeat n times
 3      for every pixel p:
 4          num ← 0 ; den ← 0
 5          for every q within radius d/2 of p:
 6              w ← exp(−‖p−q‖² / 2σs²) · exp(−δ² / 2σr²),   δ = |ΔR| + |ΔG| + |ΔB| between J(p), J(q)
 7              num ← num + w · J(q) ;  den ← den + w
 8          J'(p) ← num / den
 9      J ← J'
10  return J
```

(The implementation is OpenCV's `cv2.bilateralFilter`, which does exactly this.)

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `n` (passes) | **Smoothing passes** in the app · `--smooth-iters` · `smooth_iters` | 3 (low) · 2 (medium) · 1 (high); slider range 0–6 | More passes: flatter, cleaner, fewer tiny regions, but fine detail erodes |
| `d` | `smooth()` argument | 9 px (radius 4) | Window size |
| `σr` | `smooth(sigma_color=...)` | 35 | How different two colours must be before they stop being averaged |
| `σs` | `smooth(sigma_space=...)` | 7 px | How quickly the weight falls off with distance |

Only `n` is exposed in the interface; `d`, `σr`, `σs` are fixed in code.

## Cost and behaviour

Each pass costs `O(N · d²)` for `N` pixels, which is small compared with the labelling step. The app and CLI pass the detail preset's pass count (3 / 2 / 1) to *both* methods. The function defaults differ slightly (`kmeans_potts`: 3, `slic_merge`: 2) and only apply when the functions are called directly from code.

### What we measured

Medium detail (1200 px), k-means + Potts, on a night photograph of a river with lit buildings:

| Passes | Regions | Mean ΔE from photo | What it looks like |
|---|---|---|---|
| 0 | 407 | 9.44 | Boundaries look blocky and rectangular (JPEG 8×8 block artefacts and noise are treated as structure) |
| 1 | 454 | 9.17 | Crisp; lamp starbursts, windows and bridge arches survive |
| 2 | 473 | 9.04 | Best colour fidelity; slightly softer facades |
| 4 | 495 | 9.09 | Fine detail gone: windows become haze, lamp posts nearly vanish |

Counter-intuitively the region count *rises* with smoothing here. A plausible explanation: with noise, the cleanup stage merges a lot of speckle into neighbours, losing some real regions with it; smoothing removes the speckle first so real regions survive. This was not isolated experimentally.

**Rule of thumb:** 1–2 passes for detailed output, 3 for chunky easy-to-paint output, 0 only for already clean sources.

## Pitfalls

- It is a *colour-space* filter in RGB; it knows nothing about objects. Thin bright details close in colour to their surroundings (a white wire against a pale sky) can be absorbed.
- Over-smoothing also hurts the Potts step: it reduces the edge contrast the pairwise term relies on (see 04).

## Code and references

- `pbn/backend/imageops.py` → `smooth`
- C. Tomasi, R. Manduchi, "Bilateral filtering for gray and color images", ICCV 1998.
