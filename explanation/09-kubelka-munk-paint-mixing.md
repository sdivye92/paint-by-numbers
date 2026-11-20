# 09 · Kubelka–Munk paint mixing

## What it does and why it is here

To suggest a recipe you must be able to *predict* what a mix of tubes will look like. Averaging RGB values gets this badly wrong: real paints mix **subtractively** (blue plus yellow gives green, not grey; a drop of black darkens white a lot). This step implements a small physical model of paint, **Kubelka–Munk theory**, adapted to work from nothing more than each tube's on-screen colour.

## The idea

A layer of paint does two things to light:

- it **absorbs** some of it (coefficient `K`), which is what gives pigment its colour, and
- it **scatters** some of it back (coefficient `S`), which is what makes paint opaque and bright.

For a layer thick enough to hide what is underneath, the colour you see (its reflectance `R`) depends only on the ratio `K/S`. Crucially, when you mix paints, **`K` and `S` add up in proportion to how much of each you use**, and the mixture's colour then follows from the combined `K/S`. That additivity is what makes the theory practical.

## The maths

**Reflectance from the absorption/scattering ratio** (opaque layer):

```
R = 1 + K/S − sqrt( (K/S)² + 2·(K/S) )
```

**Inverse**, used to get a tube's `K/S` from its colour:

```
K/S = (1 − R)² / (2R)
```

**Mixing.** With volume fractions `w_i = parts_i / Σ parts`, absorption `K_i` and scattering `S_i` per tube:

```
K_mix = Σ_i w_i · K_i
S_mix = Σ_i w_i · S_i
R_mix = 1 + K_mix/S_mix − sqrt( (K_mix/S_mix)² + 2·K_mix/S_mix )
```

### How this project adapts it

Real KM work uses measured spectra at many wavelengths. We only have a tube's on-screen colour, so the model runs **per RGB channel in linear light** (the gamma of sRGB is removed first, see 01) as a coarse three-band version:

1. Each tube has a **masstone** `(R, G, B)` (its colour straight from the tube) and a relative **scattering power** `scatter_i`.
2. Linearise the masstone; clamp each channel to `[0.002, 0.995]` so `K/S` stays finite for channels that are almost zero.
3. Per channel: `ks_i = (1 − R_i)² / (2 R_i)`.
4. Set `S_i = scatter_i` (one number per tube, used for all channels) and `K_i = ks_i · S_i`.
5. For a mix with fractions `w_i`: `K_mix = Σ w_i K_i`, `S_mix = Σ w_i S_i`, `ks_mix = K_mix / S_mix`, then `R_mix` from the formula above, then back to sRGB.

**Why a separate scattering power matters.** Titanium white scatters strongly and absorbs almost nothing; a transparent pigment such as phthalo blue scatters little. In a mix, the strong scatterer sets the "background brightness" and the others tint it. If every tube had the same `S`, a speck of black would swamp a big pot of white. Worked through for 20 parts white + 1 part black:

| | Titanium White (S = 1.0) | Mars Black (S = 0.15) |
|---|---|---|
| linear R (r, g, b) | 0.930, 0.930, 0.905 | 0.0130, 0.0116, 0.0116 |
| K/S (r, g, b) | 0.003, 0.003, 0.005 | 37.5, 42.1, 42.1 |
| K = (K/S)·S | 0.003, 0.003, 0.005 | 5.63, 6.31, 6.31 |

```
K_mix  (parts-weighted sum) = 20·K_white + 1·K_black = ( 5.68, 6.36, 6.41 )
S_mix  (parts-weighted sum) = 20·1.0 + 1·0.15         = 20.15
K/S    = ( 0.282, 0.316, 0.318 )
R_lin  = ( 0.480, 0.461, 0.459 )    →  sRGB ( 184, 181, 181 )   a light neutral grey
```

With equal scattering for all tubes the same mix would come out at about sRGB (119, 115, 115), far too dark. The 12-tube defaults below set realistic relative scattering for that reason.

More examples from the model:

| Mix (by volume) | Predicted sRGB | Reads as |
|---|---|---|
| 1 black : 1 white | (82, 79, 79) | dark grey |
| 1 black : 20 white | (184, 181, 181) | light grey |
| 1 cadmium red : 3 white | (237, 94, 77) | salmon / coral |
| 8 cadmium yellow light : 1 ultramarine | (110, 122, 11) | olive green |
| 1 cadmium yellow light : 1 ultramarine | (53, 62, 14) | very dark olive |

## The algorithm

```
Algorithm 9  Predicted colour of a mix  (paints.mix_rgb)
Input : tubes with masstone sRGB c_i and scatter S_i ; parts vector p (or a batch of them)
Output: predicted sRGB of the mixture

 1  for each tube i:
 2      R_i ← clamp( linearise(c_i / 255), 0.002, 0.995 )                (per channel)
 3      ks_i ← (1 − R_i)² / (2 R_i) ;   K_i ← ks_i · S_i
 4  w ← p / Σp
 5  K ← Σ w_i K_i ;  S ← Σ w_i S_i ;  ks ← K / S                          (per channel)
 6  R ← 1 + ks − sqrt( ks² + 2 ks )
 7  return gamma-encode( R ) · 255
```

It is vectorised, so the recipe search (10) can evaluate hundreds of thousands of candidate mixes in a fraction of a second.

## The default tubes

These are approximate on-screen masstones for a typical 12-tube acrylic set, plus a relative scattering power (white is the reference). They are **editable in the app** (colour pickers, on/off) because real tubes vary by brand.

| Tube | Masstone (sRGB) | Scatter |
|---|---|---|
| Titanium White | (247, 247, 244) | 1.00 |
| Mars Black | (30, 28, 28) | 0.15 |
| Cadmium Yellow Light | (255, 222, 10) | 0.55 |
| Cadmium Yellow Medium | (255, 190, 0) | 0.55 |
| Yellow Ochre | (196, 142, 52) | 0.45 |
| Cadmium Red Medium | (215, 40, 30) | 0.55 |
| Alizarin Crimson | (120, 20, 40) | 0.20 |
| Ultramarine Blue | (28, 34, 120) | 0.25 |
| Phthalo Blue | (8, 38, 92) | 0.20 |
| Phthalo Green | (0, 66, 52) | 0.20 |
| Burnt Sienna | (125, 58, 34) | 0.35 |
| Burnt Umber | (72, 44, 32) | 0.30 |

## Parameters

| Symbol | Where it is set | Value | Effect |
|---|---|---|---|
| tube masstone | **Paint set** colour pickers in the app · `Paint(rgb=...)` | table above | The biggest lever on accuracy. Paint a thick swatch of each real tube, photograph or measure it, and enter its colour |
| tube on/off | **Paint set** checkboxes | all on | Which tubes the search may use |
| `scatter_i` | `Paint(scatter=...)` in `paints.py` | table above | Relative opacity / tinting behaviour (not exposed in the interface) |
| clamp | `_MIN_R` | 0.002 | Numerical safety for near-zero channels. Too high lifts pure colours (a phthalo green's red channel would no longer be near zero) |

## Assumptions and limits (read these before trusting a recipe)

- **Three bands, not a spectrum.** Real pigments have complex spectra; two paints that look identical can mix very differently (metamerism). Three channels capture the main behaviour, not the details.
- **One scattering number per tube** (same for all channels) and **masstone-only calibration**. Tinting behaviour at high dilution is *extrapolated* from the undiluted colour.
- **Opaque, infinitely thick layer.** Thin glazes and layering over other colours are not modelled.
- **No surface effects**, no drying shift (acrylics usually dry slightly darker), no gloss.
- **Linear in volume.** Parts are assumed to mix ideally.
- **Screen colours** are what you see; printing or photographing a swatch adds its own error.
- Darks and very strong tinters (phthalos) are the least reliable; a mixing error of a few percent changes them a lot.

Always mix a small test swatch of the important colours first.

## Code and references

- `pbn/backend/paints.py` → `Paint`, `STANDARD_SET`, `mix_rgb`, `_k_and_s`
- P. Kubelka, F. Munk, "Ein Beitrag zur Optik der Farbanstriche", *Zeitschrift für technische Physik* 12, 1931.
- G. Wyszecki, W. S. Stiles, *Color Science*, 2nd ed., 1982 (colour mixing theory).
- For a more advanced alternative using a learned pigment space, see Mixbox (Sochorová and Jamriška, SIGGRAPH Asia 2021), which this project does not use.
