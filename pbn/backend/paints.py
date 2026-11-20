"""Acrylic paint-mixing model and recipe search.

Model: single-layer Kubelka-Munk in linear RGB, per channel. Each tube is described by its
approximate masstone (the colour straight from the tube) and a relative scattering power
(opacity). From the masstone we get K/S per channel; mixtures add K and S weighted by volume:

    (K/S)_mix = sum_i c_i K_i / sum_i c_i S_i        R_mix = 1 + K/S - sqrt((K/S)^2 + 2 K/S)

This reproduces the important subtractive behaviour (yellow + blue goes green, white lightens,
a little phthalo goes a long way) but it is a coarse model: real pigments vary by brand and
batch, so treat results as a starting point and test-swatch the key colours. Tube colours are
editable for exactly that reason.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree
from skimage.color import deltaE_ciede2000
from skimage.color import rgb2lab as _sk_rgb2lab

from .imageops import rgb2lab


@dataclass(frozen=True)
class Paint:
    name: str
    rgb: tuple[int, int, int]  # approximate masstone, straight from the tube
    scatter: float  # relative scattering power: 1.0 titanium white ... ~0.2 transparent pigments


# A typical 12-tube acrylic set. Colours are approximate on-screen masstones of the standard pigments.
STANDARD_SET: tuple[Paint, ...] = (
    Paint("Titanium White", (247, 247, 244), 1.00),
    Paint("Mars Black", (30, 28, 28), 0.15),
    Paint("Cadmium Yellow Light", (255, 222, 10), 0.55),
    Paint("Cadmium Yellow Medium", (255, 190, 0), 0.55),
    Paint("Yellow Ochre", (196, 142, 52), 0.45),
    Paint("Cadmium Red Medium", (215, 40, 30), 0.55),
    Paint("Alizarin Crimson", (120, 20, 40), 0.20),
    Paint("Ultramarine Blue", (28, 34, 120), 0.25),
    Paint("Phthalo Blue", (8, 38, 92), 0.20),
    Paint("Phthalo Green", (0, 66, 52), 0.20),
    Paint("Burnt Sienna", (125, 58, 34), 0.35),
    Paint("Burnt Umber", (72, 44, 32), 0.30),
)


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(int(round(float(v))) for v in rgb))


# ------------------------------------------------------------------ mixing model
_MIN_R = 0.002  # keeps K/S finite for masstones with a zero channel (e.g. phthalo green's red)


def _to_linear(rgb255: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb255, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _to_srgb255(lin: np.ndarray) -> np.ndarray:
    lin = np.clip(lin, 0.0, 1.0)
    c = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(c * 255.0, 0, 255)


def _k_and_s(paints) -> tuple[np.ndarray, np.ndarray]:
    lin = np.clip(_to_linear([p.rgb for p in paints]), _MIN_R, 0.995)
    ks = (1.0 - lin) ** 2 / (2.0 * lin)
    S = np.array([p.scatter for p in paints], float)
    return ks * S[:, None], S


def mix_rgb(paints, parts) -> np.ndarray:
    """Predicted sRGB (0-255, float) of mixing `paints` in the given volume parts.

    `parts` is (n,) or (m, n); returns (3,) or (m, 3).
    """
    K, S = _k_and_s(paints)
    w = np.atleast_2d(np.asarray(parts, float))
    w = w / w.sum(axis=1, keepdims=True)
    ks = (w @ K) / (w @ S)[:, None]
    R = 1.0 + ks - np.sqrt(ks * ks + 2.0 * ks)
    out = _to_srgb255(R)
    return out[0] if np.ndim(parts) == 1 else out


# ------------------------------------------------------------------ recipe library
# Allowed "parts" per paint, by how many paints are in the mix (more paints -> coarser ratios).
LEVELS = {
    1: (1,),
    2: (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48),  # light tints need lots of white per drop of colour
    3: (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48),
    4: (1, 2, 3, 4, 6, 12),
}


@dataclass
class Library:
    paints: tuple[Paint, ...]
    parts: np.ndarray  # (N, n_paints) int16: parts of each paint in candidate recipe i
    rgb: np.ndarray  # (N, 3) predicted colour
    lab: np.ndarray  # (N, 3)
    n_used: np.ndarray  # (N,) number of paints in the recipe
    total: np.ndarray  # (N,) total parts
    tree: cKDTree


@lru_cache(maxsize=4)
def build_library(paints: tuple[Paint, ...], max_paints: int = 3) -> Library:
    """Enumerate every recipe of up to `max_paints` paints (in reduced integer ratios) and predict its colour."""
    n = len(paints)
    blocks = []
    for k in range(1, min(max_paints, n) + 1):
        grid = np.array(list(itertools.product(LEVELS[k], repeat=k)), dtype=np.int16)
        if k > 1:
            grid = grid[np.gcd.reduce(grid, axis=1) == 1]  # 2:4 is the same colour as 1:2
        for subset in itertools.combinations(range(n), k):
            block = np.zeros((len(grid), n), np.int16)
            block[:, list(subset)] = grid
            blocks.append(block)
    parts = np.vstack(blocks)
    rgb = mix_rgb(paints, parts)
    lab = rgb2lab(np.round(rgb).astype(np.uint8).reshape(-1, 1, 3)).reshape(-1, 3).astype(np.float64)
    return Library(paints, parts, rgb, lab, (parts > 0).sum(1), parts.sum(1), cKDTree(lab))


def match(lib: Library, target_lab, top: int = 128, w_paints: float = 1.0, w_ratio: float = 0.3):
    """Best recipe for a target CIELAB colour.

    Shortlists the nearest predicted colours, then picks by  dE2000 + a penalty for using more
    paints (`w_paints` per extra tube) and for big total ratios (`w_ratio` * log2(total parts)),
    so a simple recipe wins whenever it is about as close as a fiddly one.
    Returns (candidate index, dE2000).
    """
    target = np.asarray(target_lab, float)
    _, idx = lib.tree.query(target, k=min(top, len(lib.lab)))
    cand = lib.lab[idx]
    de = deltaE_ciede2000(np.broadcast_to(target, cand.shape), cand)
    score = de + w_paints * (lib.n_used[idx] - 1) + w_ratio * np.log2(lib.total[idx])
    j = int(np.argmin(score))
    return int(idx[j]), float(de[j])


# ------------------------------------------------------------------ 5-6 tube refinement
# Enumerating every 5-6 tube recipe is far too large (millions to tens of millions), so for
# mixes with more than 4 tubes we start from the best few library recipes and hill-climb:
# nudge one tube's parts up/down the ladder, add a tube, drop a tube, or swap one tube for another.
LADDER = (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48)
_LEVEL = {v: i for i, v in enumerate(LADDER)}


def _score_recipes(paints, parts, target_lab, w_paints, w_ratio):
    """(score, dE2000, predicted rgb) for a batch of integer recipes, using the same score as `match`."""
    parts = np.atleast_2d(parts)
    rgb = mix_rgb(paints, parts)
    lab = _sk_rgb2lab((rgb / 255.0).reshape(-1, 1, 3)).reshape(-1, 3)
    de = deltaE_ciede2000(np.broadcast_to(np.asarray(target_lab, float), lab.shape), lab)
    score = de + w_paints * ((parts > 0).sum(1) - 1) + w_ratio * np.log2(parts.sum(1))
    return score, de, rgb


def _neighbours(p: np.ndarray, max_paints: int) -> np.ndarray:
    n, k = len(p), int((p > 0).sum())
    out = []
    for j in range(n):  # step one tube's parts along the ladder (0 = leave the tube out)
        for step in (-1, 1):
            level = _LEVEL[int(p[j])] + step
            if not 0 <= level < len(LADDER) or (p[j] == 0 and k >= max_paints):
                continue
            q = p.copy()
            q[j] = LADDER[level]
            if q.sum() > 0:
                out.append(q)
    for a in np.flatnonzero(p):  # swap one tube for another, keeping its parts
        for b in np.flatnonzero(p == 0):
            q = p.copy()
            q[b], q[a] = p[a], 0
            out.append(q)
    return np.array(out, dtype=p.dtype)


def refine(lib: Library, target_lab, max_paints: int = 6, starts: int = 6,
           w_paints: float = 1.0, w_ratio: float = 0.3, max_iter: int = 60):
    """Best recipe with up to `max_paints` tubes. Returns (parts vector, dE2000, predicted rgb).

    Starts from the `starts` best library recipes (so it is never worse than `match`, scored the same
    way) and keeps the best local optimum. A fifth or sixth tube only appears if it improves the score
    by more than its per-tube penalty, so it is used for hard colours rather than everywhere.
    """
    paints = lib.paints
    target = np.asarray(target_lab, float)
    _, idx = lib.tree.query(target, k=min(128, len(lib.lab)))
    lib_score = (deltaE_ciede2000(np.broadcast_to(target, lib.lab[idx].shape), lib.lab[idx])
                 + w_paints * (lib.n_used[idx] - 1) + w_ratio * np.log2(lib.total[idx]))
    best = None
    for i in idx[np.argsort(lib_score)[:starts]]:
        cur = lib.parts[i].astype(np.int16)
        cur_score, cur_de, cur_rgb = (v[0] for v in _score_recipes(paints, cur, target, w_paints, w_ratio))
        for _ in range(max_iter):
            nb = _neighbours(cur, max_paints)
            s, de, rgb = _score_recipes(paints, nb, target, w_paints, w_ratio)
            j = int(np.argmin(s))
            if s[j] >= cur_score - 1e-6:
                break
            cur, cur_score, cur_de, cur_rgb = nb[j], float(s[j]), float(de[j]), rgb[j]
        if best is None or cur_score < best[0]:
            best = (cur_score, cur.copy(), cur_de, cur_rgb)
    _, parts, de, rgb = best
    g = int(np.gcd.reduce(parts[parts > 0]))  # 6:3:3 is the same colour as 2:1:1
    return (parts // g if g > 1 else parts), float(de), rgb
