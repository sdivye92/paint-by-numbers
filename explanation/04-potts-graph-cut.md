# 04 · Potts model and graph cut (method A)

## What it does and why it is here

After k-means has chosen the palette, every pixel must be given one of the `k` colours. The naive rule, "nearest palette colour", decides each pixel alone and leaves speckle. Method A instead finds the labelling that balances **fit** (be close to your palette colour) against **smoothness** (agree with your neighbours), and solves it *globally* with a **graph cut**. This is the largest single quality gain in the pipeline.

## The idea

Think of the image as a grid of pixels, each pixel wanting one label. Two costs compete:

- Giving a pixel a colour far from its true colour costs a lot (the **data term**).
- Giving two neighbouring pixels different labels costs something (the **smoothness term**), *except* where the photo itself has a real edge, in which case a label change is cheap.

Minimising the total cost produces smooth blobs whose boundaries follow the photo's edges.

## The maths

A **Markov random field with a Potts prior**. For a labelling `l` (one label per pixel) over the 4-connected pixel grid:

```
E(l) = Σ_p  D_p(l_p)  +  Σ_{(p,q) ∈ N}  w_pq · [ l_p ≠ l_q ]
```

`[·]` is 1 if the statement is true, else 0; `N` is the set of horizontally and vertically adjacent pixel pairs.

**Data term.** Squared Lab distance to the palette colour `c_l`, scaled:

```
D_p(l) = ‖ lab_p − c_l ‖² / s²             s = data_scale = 10
```

so `ΔE = 10` costs 1, `ΔE = 20` costs 4, `ΔE = 30` costs 9.

**Smoothness weight (contrast-sensitive).** With `d_pq = ‖ lab_p − lab_q ‖` measured on the smoothed image:

```
w_pq = λ · ( φ + (1 − φ) · exp( − (d_pq / σ)² ) )          φ = floor = 0.2,   σ = edge_sigma = 8
```

- In a flat area `d_pq ≈ 0`, so `w_pq ≈ λ`: breaking the label is expensive.
- Across a real edge `d_pq` is large, `exp(...) → 0`, so `w_pq → φ·λ = 0.2 λ`: breaking the label is cheap.
  (the `φ` floor keeps a little smoothing even on strong edges so boundaries do not get jagged).

With `d_pq` = 0, 8, 16, 24: `w/λ` = 1.00, 0.49, 0.22, 0.20.

**Special cases.**

- `λ = 0`: pairwise term vanishes; each pixel takes its nearest palette colour (plain k-means labelling).
- `λ → ∞`: the whole image becomes one label.

## Solving it: α-expansion

`E` has no closed-form minimiser, but for a Potts prior the **α-expansion** move (Boykov, Veksler, Zabih, 2001) can be solved *exactly* by a minimum cut. For a chosen label `α`, every pixel either keeps its label or switches to `α`. Let `x_p ∈ {0, 1}` (1 = switch to α).

**Unary costs.** `U_p(0) = D_p(l_p)` (keep), `U_p(1) = D_p(α)` (switch).

**Pairwise costs** for a neighbouring pair `(p, q)` with current labels `l_p, l_q`, and `w = w_pq`:

```
E00 = w · [ l_p ≠ l_q ]       both keep
E01 = w · [ l_p ≠ α   ]       p keeps, q switches
E10 = w · [ α  ≠ l_q  ]       p switches, q keeps
E11 = 0                       both switch to α
```

A binary pairwise term can be written as a graph cut if it is **submodular**: `E01 + E10 ≥ E00 + E11`. Here that is `[l_p≠α] + [α≠l_q] ≥ [l_p≠l_q]`, the triangle inequality, which holds because Potts is a metric. It decomposes exactly as

```
E(a, b) = E00 + (E10 − E00)·a + (E11 − E10)·b + (E01 + E10 − E00 − E11)·(1 − a)·b
```

i.e. two **unary terms** (added to `U_p(1)` and `U_q(1)`) plus **one non-negative directed edge** `p → q` with capacity `E01 + E10 − E00 − E11`. A source/sink graph is built:

- terminal edges encode `U_p(0)` and `U_p(1)` (shifted by `min` so capacities are ≥ 0),
- neighbour edges encode the directed capacities above.

The minimum s–t cut (Boykov–Kolmogorov max-flow, via PyMaxflow) gives the optimal `x`: pixels on the sink side switch to `α`.

```
Algorithm 3  Potts labelling by α-expansion  (potts_labels)
Input : Lab image, palette c_1 … c_k, λ, s, σ, φ, max sweeps S = 3
Output: label map l

 1  compute D_p(j) for all pixels p and labels j
 2  l_p ← argmin_j D_p(j)                      (start from "nearest colour")
 3  compute w_pq for all neighbouring pairs
 4  for sweep = 1 … S:
 5      changed ← 0
 6      for α in a random permutation of {1 … k}:
 7          build the s–t graph for the α-expansion move of l        (formulas above)
 8          x* ← minimum cut
 9          l' ← switch pixels with x*_p = 1 to α
10          changed ← changed + number of pixels that differ ;  l ← l'
11      if changed < 0.1 % of all pixels: stop
12  return l
```

**Guarantees.** Each expansion move can only lower (never raise) `E`. The result is a *strong local minimum*: no single α-expansion improves it, and for a Potts model with uniform weights its energy is within a factor of 2 of the global minimum (Boykov et al.). In practice it is far closer.

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `λ` | **Smoothness (λ)** in the app · `--lam` · `lam` | 2.0 (low) · 1.5 (medium) · 1.0 (high); slider 0–6 | The main smoothness dial. Higher: blobbier regions, fewer specks, small details lost. Lower: more detail and more fragments (cleanup then removes the tiny ones) |
| `s` | `potts_labels(data_scale=...)` | 10 ΔE | Sets the *exchange rate* between colour error and smoothness: a pixel flips label only if the colour-cost saving exceeds the boundary cost it creates |
| `σ` | `potts_labels(edge_sigma=...)` | 8 ΔE | How different two neighbours must be before the boundary counts as a "real edge" |
| `φ` | `potts_labels(floor=...)` | 0.2 | Fraction of `λ` that remains across strong edges |
| `S` | `potts_labels(sweeps=...)` | 3 | Maximum passes over all labels; usually converges in 2 |
| seed | `potts_labels(seed=...)` | 0 | Order in which labels are expanded (affects which local minimum is reached) |

Only `λ` is exposed; `s`, `σ`, `φ`, `S` are fixed in code.

A worked feel for `λ = 2` (illustrative; the real solution is global, not pixel by pixel): an isolated pixel in a flat area whose four neighbours all share another label would pay up to `4 · 2 = 8` to disagree with them. Keeping its own label is only worthwhile if its data cost for the neighbours' label is more than 8 higher than for its own, i.e. a squared-ΔE gap above `8 · s² = 800`. If it already matches its own label exactly that means the neighbours' colour must be about ΔE ≈ 28 away. Smaller differences, which is what noise produces, get smoothed away; clear differences survive.

## Cost and behaviour

Each expansion is one max-flow on a grid graph with `≈ 2 · H · W` edges. One sweep does `k` expansions, so time grows with pixels × colours. Total method-A times measured on the author's laptop (smoothing + k-means + Potts + cleanup; yours will differ):

| Image (working size) | Colours | Time |
|---|---|---|
| 600 × 400 | 16 | 2.3 s |
| 512 × 512 | 16 | 2.7 s |
| 800 × 530 | 24 | 7.6 s |
| 1200 × 800 | 20 | 10 s (Potts ≈ 8 s of it) |
| 1600 × 1060 | 24 | 23.5 s |

Memory is dominated by the data-cost array of size `H · W · k` (float32).

## What we learned

- The Potts term is what keeps the later cleanup (07) a light touch: it removes most speckle and ragged boundaries *before* regions are tested for size, instead of leaving the cleanup to repaint them.
- The contrast-sensitive weight is a design choice rather than something we ablated: a constant `w_pq` would smooth across real edges as readily as across noise, which is exactly what the `exp(−(d/σ)²)` factor avoids.
- The binary decomposition above was verified against brute force (`tests/test_potts.py`): the graph-cut move equals the best of all `2⁹` keep/switch assignments on random 3×3 grids, and total energy never rises.

## Code and references

- `pbn/backend/potts.py` → `potts_labels`, `expand`, `pair_weights`, `data_costs`, `energy`
- Y. Boykov, O. Veksler, R. Zabih, "Fast approximate energy minimization via graph cuts", *IEEE TPAMI* 23(11), 2001.
- Y. Boykov, V. Kolmogorov, "An experimental comparison of min-cut/max-flow algorithms for energy minimization in vision", *IEEE TPAMI* 26(9), 2004.
- V. Kolmogorov, R. Zabih, "What energy functions can be minimized via graph cuts?", *IEEE TPAMI* 26(2), 2004 (the submodularity condition).
