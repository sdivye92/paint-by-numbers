# 10 · Recipe search: finding the best tube mix

This is the project's optimisation: for each palette colour, find the mix of your tubes whose predicted colour (09) is closest to it, without being fiddly to make.

## What it does and why it is here

Each numbered colour is matched **independently** to a recipe: a small number of tubes in simple volume ratios. Closeness is judged by perceptual colour difference (ΔE2000, see 01). Simplicity is judged by how many tubes are involved and how large the ratios are.

## The idea

Two regimes, chosen by "Max tubes per mix":

- **Up to 4 tubes: brute force.** Enumerate every sensible recipe once, predict its colour, and look up the best ones near the target with a spatial index. Because it is exhaustive over the allowed ratios, the result is essentially the optimum.
- **5–6 tubes: local search.** Too many recipes to list, so start from the best 4-tube recipes and improve them by repeated small changes (hill climbing).

Not used: gradient descent, genetic algorithms, simulated annealing, least squares. Whole-number "parts" are the natural unit for someone measuring paint with a spoon, and the discrete search space is small enough to handle with the two methods above.

## The maths

**Variables.** For the `n` enabled tubes, an integer vector `p ∈ ℕⁿ` of *parts*, where each `p_i` comes from the **ladder**

```
LADDER = { 0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48 }          0 = tube not used
```

with at most `m` non-zero entries (`m` = "Max tubes per mix", 2 – 6) and `Σp > 0`. Fractions are `w = p / Σp`.

**Prediction.** `mix(p)` is the Kubelka–Munk colour from 09, converted to CIELAB.

**Objective (minimised for each target colour `t`).**

```
J(p) = ΔE2000( t, Lab(mix(p)) )  +  λ · (k(p) − 1)  +  ρ · log2( Σp )

k(p) = number of tubes with p_i > 0
λ    = penalty per extra tube      (Recipe style; default 1.0)
ρ    = 0.3                          (penalty on large ratios; fixed)
```

Reading it: the first term is colour error. The second charges `λ` for each tube beyond the first. The third charges for big total ratios (`log2`: 2 parts costs 0.3, 16 parts 1.2, 49 parts 1.7), because "48 white + 1 sienna" is harder to measure than "2 white + 1 sienna".

**Worked example.** Lightest palette colour of the coffee photo, `sRGB (244, 227, 211)`, with `λ = 1`, `ρ = 0.3`:

| Candidate recipe | Predicted sRGB | ΔE2000 | tube term | ratio term | **J** |
|---|---|---|---|---|---|
| white only | (247, 247, 244) | 8.87 | 0 | 0 | **8.87** |
| 24 white + 1 sienna | (231, 199, 170) | 8.32 | 1.0 | 1.39 | 10.71 |
| **48 white + 1 sienna** | (237, 214, 191) | 4.12 | 1.0 | 1.68 | **6.80** (chosen) |
| 48 white + 1 sienna + 1 ochre | (236, 212, 178) | 6.91 | 2.0 | 1.69 | 10.60 |

The 48:1 recipe wins because the colour gain (8.87 → 4.12) outweighs its 2.68 of complexity penalty, while adding a third tube makes things worse.

## The algorithm

### A · Exhaustive library (≤ 4 tubes)

```
Algorithm 10  Build the recipe library  (paints.build_library)
Input : n enabled tubes, maximum tubes per mix m ≤ 4
Output: table of candidate recipes with predicted colours, and a k-d tree over their Lab colours

 1  levels[1] ← {1}
    levels[2] ← levels[3] ← {1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48}
    levels[4] ← {1, 2, 3, 4, 6, 12}
 2  for k = 1 … m:
 3      grid ← all k-tuples of levels[k]
 4      if k > 1:  keep only tuples with gcd = 1                 (2:4 is the same colour as 1:2)
 5      for every subset of k tubes:
 6          add one recipe per tuple (parts placed on the subset, zero elsewhere)
 7  predict the colour of every recipe with Algorithm 9 ; convert to 8-bit sRGB, then Lab
 8  index the Lab colours in a k-d tree
 9  return the table and the tree
```

For all 12 default tubes the library holds **2,058** recipes for ≤ 2 tubes, **121,078** for ≤ 3 and **603,703** for ≤ 4, built in about 0.1–0.3 s and cached per paint set.

```
Algorithm 11  Match a colour  (paints.match)
Input : target Lab colour t, library, shortlist size T = 128, λ, ρ
Output: best recipe and its ΔE2000

 1  S ← the T library colours nearest to t in Lab (k-d tree, Euclidean ΔE76)
 2  for each recipe r in S:  score(r) ← ΔE2000(t, colour(r)) + λ (k(r) − 1) + ρ log2(Σ parts(r))
 3  return the recipe with the lowest score
```

The shortlist uses the cheap ΔE76 only to *find candidates*; the final ranking uses ΔE2000. The one gap in optimality is that a candidate better under ΔE2000 but outside the 128 nearest by ΔE76 would be missed.

### B · Local search (5–6 tubes)

```
Algorithm 12  Refine by local search  (paints.refine)
Input : target t, library (≤ 4 tubes), maximum tubes m (5 or 6), starts = 6, λ, ρ, max_iter = 60
Output: recipe, its ΔE2000, its predicted colour

 1  starts_list ← the 6 best library recipes for t under the score J
 2  best ← none
 3  for each start recipe p in starts_list:
 4      repeat up to max_iter times:
 5          N ← neighbours(p, m)
 6          q ← the neighbour with the lowest J
 7          if J(q) ≥ J(p) − 1e-6:  break                      (local optimum)
 8          p ← q
 9      if J(p) < J(best):  best ← p
10  divide best by the gcd of its non-zero parts
11  return best

neighbours(p, m):
    for each tube i:       move p_i one step up or down the LADDER
                           (starting a tube, 0 → 1, only if fewer than m tubes are in use)
    for each used tube a and unused tube b:   swap  (move a's parts onto b, set a to 0)
```

This is steepest-descent hill climbing with six restarts. Because every start is a library recipe scored the same way, it is **never worse than the 4-tube answer**. Every accepted move strictly lowers `J`, so each climb terminates. It can end in a local optimum; it is not guaranteed to find the global one.

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `m` | **Max tubes per mix** in the app · `--max-paints` · `max_paints` | 3 (default); 2 – 6 | Size of the search space. 2 – 4 use the exhaustive library; 5 – 6 use local search |
| `λ` | **Recipe style** · `--tube-penalty` · `tube_penalty` | Simplest 1.0 (default) · Balanced 0.5 · Accurate 0.25 · Most accurate 0.1 | How much accuracy you want in exchange for extra tubes. Lower values let more tubes appear |
| `ρ` | `match(w_ratio=...)`, `refine(w_ratio=...)` | 0.3 | Penalty on large ratios (fixed) |
| `T` | `match(top=...)` | 128 | Size of the shortlist |
| starts, max_iter | `refine(starts=..., max_iter=...)` | 6, 60 | Restarts and iteration cap of the local search |
| ladder / levels | `LADDER`, `LEVELS` in `paints.py` | see above | The allowed ratios. 48:1 (about a 2% tint) is the finest. Finer tints are impractical to measure anyway |
| paint set | **Paint set** in the app | 12 tubes | Which tubes may appear; their colours feed Algorithm 9 |
| quality label | `Recipe.quality` | ΔE2000 < 2 excellent · < 5 good · otherwise approximate | What the table and warnings show |

`λ` and `m` work together: `m` is the cap, and `λ` decides how readily the search reaches it.

## Cost

Library build: about 0.1 s (≤ 3 tubes) to 0.3 s (≤ 4 tubes), once per paint set. Once the library exists, matching all 16 palette colours takes well under 0.1 s (a k-d tree query plus 128 ΔE2000 evaluations each). The 5–6 tube local search added roughly 0.04 s for 16 colours.

## What we measured

16-colour palettes from three photos (cat, coffee, astronaut) with the default 12 tubes, `λ = 1`:

| Max tubes | Coffee mean ΔE | Coffee bad (ΔE ≥ 5) | Astronaut mean ΔE | Astronaut bad |
|---|---|---|---|---|
| 2 | 3.37 | 2 | 4.45 | 5 |
| 3 | 1.65 | 0 | 1.82 | 1 |
| 4 | 1.65 | 0 | 1.72 | 1 |
| Ideal reference: all 12 tubes, any continuous ratio | 0.63 | 0 | 0.34 | 0 |

The ideal row used a continuous optimiser (SciPy Powell over softmax weights) purely as an analysis benchmark; it is **not** part of the app.

Findings:

1. **Two to three tubes is a big jump; three to four is almost nothing** at the default penalty.
2. **The per-tube penalty matters more than the cap.** Cat photo, up to 6 tubes allowed:

   | λ | Mean ΔE | Worst ΔE | Recipes using 4 tubes |
   |---|---|---|---|
   | 1.0 | 1.36 | 2.9 | 1 of 16 |
   | 0.5 | 0.94 | 2.1 | 6 of 16 |
   | 0.25 | 0.81 | 1.3 | 9 of 16 |
   | 0.1 | 0.73 | 1.3 | 13 of 16 |

3. **Five and six tubes were almost never chosen.** Even at λ = 0.1 only 2 of 16 coffee colours used five tubes and none used six; the other photos used none.
4. **The "ideal" gain was mostly about ratios, not tubes.** The hardest colour tested was a very pale grey, sRGB (228, 221, 221): white alone has ΔE 6.5. A near-perfect match needs about a 0.5% tint of dark pigment (roughly 1 : 200), beyond the 48 : 1 ladder and, honestly, beyond what can be measured by eye. More tubes did not help it.

Takeaway: for these photos and this tube set, `Accurate` with 4 tubes buys most of the available accuracy; 5–6 tubes is there when you want it, but rarely changes the answer.

## Pitfalls

- The search optimises the *model's* prediction. Any error in the model (09) carries straight into the recipe.
- Per-colour independence means two similar palette colours might get unrelated recipes. That is accurate but may mean more tubes in use overall; the "Total paint needed" table shows the consequence.
- Saturated colours outside what the tubes can mix are returned as the closest achievable and flagged "approximate".

## Code and references

- `pbn/backend/paints.py` → `build_library`, `match`, `refine`, `_neighbours`, `_score_recipes`
- `pbn/backend/recipes.py` → `build_recipes`
- J. L. Bentley, "Multidimensional binary search trees used for associative searching", *Communications of the ACM* 18(9), 1975 (the k-d tree).
- S. Russell, P. Norvig, *Artificial Intelligence: A Modern Approach*, ch. 4 (hill climbing with random restarts).
