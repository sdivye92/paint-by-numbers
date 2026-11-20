# 03 · k-means palette

## What it does and why it is here

k-means chooses the **palette**: the `k` colours that best summarise the photo. Method A runs it over (a sample of) all pixels. Method B runs a *weighted* version over region average colours. The final numbered paints come from this step (then adjusted by `finalize`).

## The idea

Imagine the image's pixels as a cloud of points in Lab colour space. Pick `k` centre points so that every pixel is close to its nearest centre. Those centres are the paints; "belonging to centre 7" means "paint with colour 7".

## The maths

Given points `x_1 … x_n` in Lab, find centres `μ_1 … μ_k` minimising the **within-cluster sum of squares**:

```
J(μ) = Σ_i  ‖ x_i − μ_{c(i)} ‖²          where  c(i) = argmin_j ‖ x_i − μ_j ‖
```

This is NP-hard in general, so it is solved to a local optimum with **Lloyd's algorithm** (alternate assignment and update), which never increases `J`.

**Weighted variant** (method B): each point carries a weight `w_i` (the region's area in pixels):

```
J_w(μ) = Σ_i  w_i · ‖ x_i − μ_{c(i)} ‖²        →  centre = weighted mean of its members
```

**k-means++ seeding** avoids poor starts. Let `D(x)` be the distance from `x` to the nearest centre chosen so far:

```
centre 1       : chosen uniformly at random
centre j+1     : chosen with probability  D(x)² / Σ_y D(y)²
```

This makes the expected cost `O(log k)`-competitive with the optimum (Arthur and Vassilvitskii, 2007) and in practice gives much better palettes than uniform random seeds.

## The algorithm

```
Algorithm 2  k-means with k-means++ seeding (as used in kmeans_palette)
Input : points X (Lab, subsampled to ≤ 100 000), k, restarts R = 4, seed
Output: centres μ_1 … μ_k

 1  best ← ∞
 2  repeat R times
 3      choose μ_1 uniformly from X
 4      for j = 2 … k:  choose μ_j from X with probability ∝ D(x)²       (k-means++)
 5      repeat until assignments stop changing (or 300 iterations):
 6          for every x: c(x) ← index of the nearest centre              (assign)
 7          for every j:  μ_j ← mean of { x : c(x) = j }                 (update)
 8      if J(μ) < best:  keep these centres
 9  return best centres
```

Pixels are then assigned to centres (method A: by the Potts step, see 04; method B: by region, see 06).

## After clustering: `finalize`

`result.finalize` post-processes whatever the labelling stage produced:

1. Drops palette entries that no pixel ended up using (cleanup can remove a colour entirely).
2. **Recomputes each palette colour as the mean Lab of the pixels it actually covers**: the Potts and cleanup steps move pixels around, so the original cluster centre is no longer the best description.
3. **Sorts the palette dark → light by L** and renumbers, so number 1 is always the darkest paint and the numbering is stable and easy to learn.

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `k` | **Colours** in the app · `-k`, `--colors` | 16 (low) · 20 (medium) · 24 (high); slider 2–48 | Upper bound on the number of paints. More colours: closer to the photo, more regions, more paints to mix. The final count can be lower than `k` if a colour ends up unused |
| `R` | `kmeans_palette` (`n_init`) | 4 | Restarts; guards against a bad seed |
| sample size | `kmeans_palette(sample=...)` | 100 000 pixels | Speed; very rare colours (a tiny red flag) can be under-represented |
| seed | `kmeans_palette(seed=...)` | 0 | Makes results reproducible |
| weights | method B | region area | Big regions pull centres more than tiny ones |
| `k` in method B | `min(k, number of regions)` | | Cannot ask for more colours than regions |

## Cost and behaviour

Each Lloyd iteration costs `O(n · k)`. On a 100k sample it takes a fraction of a second (the `kmeans` timing in the app is typically 0.2–0.3 s).

## Pitfalls and lessons

- **k-means ignores where pixels are.** Two neighbouring pixels of nearly equal colour can land in different clusters, giving salt-and-pepper speckle. That is the reason the project adds spatial steps afterwards: bilateral smoothing (02), the Potts term (04), or SLIC and region merging (05, 06).
- Detail gets absorbed: a small bright highlight is only a few pixels, so it barely influences the cost and is rarely given its own centre unless `k` is large.
- Palette colours are *averages*, so they are slightly less saturated than the most vivid pixels. This is normal for any quantiser.

## Code and references

- `pbn/backend/methods.py` → `kmeans_palette`, and the weighted fit inside `slic_merge`
- `pbn/backend/result.py` → `finalize`
- S. Lloyd, "Least squares quantization in PCM", *IEEE Trans. Information Theory* 1982; D. Arthur, S. Vassilvitskii, "k-means++: the advantages of careful seeding", SODA 2007.
