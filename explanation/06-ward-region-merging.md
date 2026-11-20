# 06 · Ward region merging (method B)

## What it does and why it is here

SLIC leaves a few thousand tiny superpixels. **Ward merging** repeatedly joins the two neighbouring blobs that are cheapest to join, until a target number of regions remains. It is how method B gives you direct control over the number of regions. After merging, the regions get their palette colours (weighted k-means, see 03) and go to cleanup (07).

## The idea

Treat the superpixels as nodes in a graph (the **region adjacency graph**), with an edge between every two blobs that touch. Merging blobs always makes the average colour of the result a worse description of its pixels; Ward's method picks, at each step, the merge that makes things *least* worse. Small blobs and blobs of very similar colour merge first; large or very different blobs resist.

## The maths

Let a region `a` have `n_a` pixels and mean colour `μ_a` (Lab). The **within-region sum of squares** is `SSE(a) = Σ_{x ∈ a} ‖x − μ_a‖²`. Merging `a` and `b` increases total SSE by exactly

```
Δ(a, b) = ( n_a · n_b / (n_a + n_b) ) · ‖ μ_a − μ_b ‖²
```

(derivation: `SSE(a ∪ b) − SSE(a) − SSE(b)`, expanded around the merged mean `μ = (n_a μ_a + n_b μ_b) / (n_a + n_b)`; the cross terms cancel and what is left is the expression above.)

Reading the formula: the cost grows with the colour gap squared and with the *harmonic-mean-like* size factor `n_a n_b / (n_a + n_b)`. Two tiny blobs of different colour are cheap to merge; two big blobs of even a mild colour difference are expensive. After a merge:

```
n_ab  = n_a + n_b
μ_ab  = ( n_a μ_a + n_b μ_b ) / n_ab
```

## The algorithm

Greedy agglomeration with a priority queue. Entries can become stale when a region changes, so each region has a **version counter** and stale entries are skipped when popped (lazy deletion).

```
Algorithm 5  Ward merging on a region adjacency graph  (ward_merge)
Input : superpixel label map, Lab image, target region count N
Output: merged label map

 1  for every region i:  n_i ← pixel count ;  μ_i ← mean Lab ;  version_i ← 0
 2  adjacency ← pairs of regions that share a pixel edge (4-neighbour)
 3  heap ← { ( Δ(a,b), a, b, version_a, version_b )  for every adjacent pair }
 4  regions ← number of regions
 5  while regions > N and heap not empty:
 6      pop ( Δ, a, b, va, vb ) with the smallest Δ
 7      if a or b is no longer alive, or version_a ≠ va, or version_b ≠ vb:  continue     (stale)
 8      merge b into a:  n_a ← n_a + n_b ;  μ_a ← weighted mean ;  mark b dead
 9      neighbours(a) ← neighbours(a) ∪ neighbours(b) \ {a, b}
10      for every neighbour x of b:  replace b by a in x's neighbour set
11      version_a ← version_a + 1 ;  regions ← regions − 1
12      for every neighbour x of a:  push ( Δ(a,x), a, x, version_a, version_x )
13  return the label map with every region replaced by its surviving representative
```

Complexity: with `E` adjacent pairs, `O(E log E)`. For 4000–20000 superpixels that is a few hundred milliseconds in Python.

## From regions to colours

Once there are `N` regions the palette is chosen over the **regions**, not the pixels: a weighted k-means (03) over the regions' mean colours with weights equal to their pixel counts. Each region takes its nearest palette colour. Neighbouring regions that ended up with the same colour are now one connected area of that colour. Then cleanup (07) runs.

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| `N` | **Target regions** · `--regions` · `regions` | 300 (low) · 800 (medium) · 1800 (high); slider 50–4000 | How many regions the colour-agnostic merge stops at |

**`N` is a ceiling, not the final count.** After colours are assigned, same-coloured neighbours fuse and cleanup removes small and thin regions, so the final number is lower:

| Photo / preset | `N` | Final regions (method B) |
|---|---|---|
| coffee, low | 300 | 87 |
| astronaut, low | 300 | 125 |
| cat, low | 300 | 105 |
| night river, low (24 colours) | 300 | 196 |
| night river, medium | 800 | 437 |
| night river, high | 1800 | 912 |

Treat `N` as "how much detail may survive"; the exact count depends on the picture.

## Pitfalls

- Ward uses only colour. It can join two blobs of the same colour across a thin dark gap, or fuse a small bright detail into a neighbour if it is similar enough. Cleanup then enforces size and width, but it cannot restore detail the merge discarded.
- Because the cost favours merging *small* blobs, fine detail disappears first when `N` is low, which is usually what you want.

## Code and references

- `pbn/backend/methods.py` → `ward_merge`, `slic_merge`; `pbn/backend/regions.py` → `adjacency`
- J. H. Ward, "Hierarchical grouping to optimize an objective function", *J. American Statistical Association* 58(301), 1963.
