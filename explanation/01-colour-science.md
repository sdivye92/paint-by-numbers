# 01 · Colour science: CIELAB and ΔE

## What it does and why it is here

Almost every decision in this project is "are these two colours close?": which palette colour does a pixel belong to, which two palette colours should absorb a tiny region, which paint mix is closest to a target. RGB distances are a poor answer to that question, so the project works in **CIELAB** and measures differences with **ΔE**.

## The idea

RGB numbers describe how much light a screen emits, not how a human sees colour. Two RGB pairs that are the same Euclidean distance apart can look nearly identical (in dark blues) or clearly different (in greens). CIELAB was designed so that equal numeric steps look roughly like equal perceptual steps. It has three axes:

- **L**: lightness, 0 (black) to 100 (white)
- **a**: green (−) to red (+)
- **b**: blue (−) to yellow (+)

## The maths

**1. Linearise sRGB.** Screens apply a gamma curve; light mixes linearly, so undo it first. For each channel `c` in [0, 1]:

```
c_lin = c / 12.92                          if c ≤ 0.04045
c_lin = ((c + 0.055) / 1.055) ^ 2.4        otherwise
```

**2. Linear RGB → XYZ** (sRGB primaries, D65 white):

```
X = 0.4124 R + 0.3576 G + 0.1805 B
Y = 0.2126 R + 0.7152 G + 0.0722 B
Z = 0.0193 R + 0.1192 G + 0.9505 B
white point:  Xn = 0.9505   Yn = 1.0   Zn = 1.0890
```

**3. XYZ → Lab.**

```
f(t)  = t ^ (1/3)                          if t > (6/29)^3
f(t)  = t / (3 (6/29)^2) + 4/29            otherwise

L = 116 f(Y/Yn) − 16
a = 500 [ f(X/Xn) − f(Y/Yn) ]
b = 200 [ f(Y/Yn) − f(Z/Zn) ]
```

**4. Colour difference.**

*ΔE76*, the plain Euclidean distance in Lab:

```
ΔE76 = sqrt( (L1−L2)² + (a1−a2)² + (b1−b2)² )
```

*ΔE2000* (CIEDE2000) corrects ΔE76's known weaknesses (too sensitive to chroma differences, uneven in blues, over-weights lightness differences far from mid-grey). In outline:

```
ΔE00 = sqrt( (ΔL' / (kL·SL))²  +  (ΔC' / (kC·SC))²  +  (ΔH' / (kH·SH))²
             +  RT · (ΔC' / (kC·SC)) · (ΔH' / (kH·SH)) )

a'  = (1 + G) · a,   G = 0.5 · (1 − sqrt( C̄^7 / (C̄^7 + 25^7) ))     (boosts low-chroma colours)
SL  = 1 + 0.015 (L̄ − 50)² / sqrt(20 + (L̄ − 50)²)
SC  = 1 + 0.045 C̄'
SH  = 1 + 0.015 C̄' T
RT  = rotation term that fixes the blue region
kL = kC = kH = 1
```

`ΔL'`, `ΔC'`, `ΔH'` are the differences in lightness, chroma and hue computed from the adjusted `a'`; `T` is a hue-dependent weight. The full definition is in Sharma, Wu and Dalal (2005); the project calls `skimage.color.deltaE_ciede2000`.

Rule of thumb used in the app's labels:

| ΔE2000 | How it looks | Label in the recipe table |
|---|---|---|
| < 1 | indistinguishable | excellent (< 2) |
| 1 – 2 | only visible side by side | excellent |
| 2 – 5 | noticeable | good (< 5) |
| ≥ 5 | clearly different | approximate |

## The algorithm

```
Algorithm C1  Colour conversion and colour difference  (imageops.rgb2lab, skimage ΔE2000)
Input : 8-bit sRGB colours (or an image) ; for a comparison, two Lab colours
Output: Lab colours ; ΔE

 1  c ← rgb / 255
 2  c_lin ← c / 12.92  where c ≤ 0.04045,  else ((c + 0.055) / 1.055) ^ 2.4           (undo gamma)
 3  (X, Y, Z) ← M · c_lin ,  M = the sRGB → XYZ matrix above
 4  fx, fy, fz ← f(X/Xn), f(Y/Yn), f(Z/Zn)
 5  L ← 116 fy − 16 ;  a ← 500 (fx − fy) ;  b ← 200 (fy − fz)
 6  ΔE76 (p, q)   ← sqrt( (Lp−Lq)² + (ap−aq)² + (bp−bq)² )
 7  ΔE2000 (p, q) ← the CIEDE2000 formula above      (steps: adjust a → a', then C', h', ΔL', ΔC', ΔH', weights SL SC SH, rotation RT)
```

## Parameters

Colour science has almost no tunable settings here: the conversion is fixed (sRGB, D65). What *can* be tuned is how the measures are used:

| What | Where | Value | Effect |
|---|---|---|---|
| Recipe quality thresholds | `Recipe.quality` | ΔE2000 < 2 excellent · < 5 good · otherwise approximate | The labels and "approximate" warnings in the recipe table |
| Colour-error exchange rate in the Potts data term | `potts_labels(data_scale=...)` | 10 ΔE per cost unit (cost = ΔE² / 100) | How strongly colour mismatch is punished against smoothness (see 04) |
| Edge sensitivity in the Potts weight | `potts_labels(edge_sigma=...)` | 8 ΔE | Which neighbour differences count as a real edge (see 04) |
| Recipe shortlist metric and size | `match(top=...)` | ΔE76, 128 candidates | Cheap candidate search before the exact ΔE2000 ranking (see 10) |

None of these is exposed in the interface; they are named constants in the code.

## Where each measure is used

| Place | Measure | Why |
|---|---|---|
| k-means (palette and cluster assignment) | Euclidean in Lab (= ΔE76), squared | Cluster means are only meaningful under Euclidean distance |
| Potts data term | squared ΔE76 to a palette colour, divided by `data_scale²` | Same reason; see 04 |
| Potts pairwise weight | ΔE76 between neighbouring pixels | Detects real edges; see 04 |
| Ward merging | squared ΔE76 between region means | Variance-based cost; see 06 |
| Region cleanup | ΔE76 between palette colours | Picks the closest-looking neighbour colour; see 07 |
| Recipe shortlist (k-d tree) | ΔE76 | The tree needs a Euclidean metric |
| Recipe objective | **ΔE2000** | Final ranking should follow perception most closely; see 10 |
| Mean error shown in the app (`mean_dE`, "colour difference from photo") | mean ΔE76 per pixel | Simple, cheap, comparable between methods |

## Implementation notes

- The image pipeline converts with OpenCV (`cv2.cvtColor` on float32 RGB in [0, 1], `COLOR_RGB2Lab`), giving L in [0, 100] and a, b roughly in [−127, 127]. The reverse conversion turns palette colours back into sRGB.
- Predicted paint-mix colours are rounded to 8-bit sRGB before conversion to Lab when building the recipe library (so the library stores exactly what a screen would show). The local-search refinement scores in float Lab using scikit-image.

## What we learned

- Doing k-means in Lab rather than RGB gives visibly better palettes for the same `k`: skin tones and skies keep their subtle gradations instead of collapsing into muddy averages.
- ΔE76 is good enough for clustering, but not for final ranking of near-identical candidates, which is why the recipe objective uses ΔE2000.

## Code and references

- `pbn/backend/imageops.py` (`rgb2lab`, `lab2rgb`), `pbn/backend/paints.py` (`match`), `pbn/backend/compare.py` (`metrics`)
- CIE 15:2004 *Colorimetry*; G. Sharma, W. Wu, E. N. Dalal, "The CIEDE2000 color-difference formula: implementation notes, supplementary test data, and mathematical observations", *Color Research & Application* 30(1), 2005.
