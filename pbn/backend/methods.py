"""The two paint-by-numbers pipelines.

A. kmeans-potts : smooth -> Lab k-means palette -> Potts graph-cut labelling -> min-area/width cleanup
B. slic-merge   : smooth -> SLIC superpixels -> Ward region merging to N regions
                  -> weighted k-means palette over the regions -> min-area/width cleanup
"""
from __future__ import annotations

import heapq
import time

import numpy as np
from sklearn.cluster import KMeans
from skimage.segmentation import slic

from .imageops import rgb2lab, smooth
from .potts import potts_labels
from .regions import adjacency, clean_regions
from .result import Result, finalize


def kmeans_palette(lab: np.ndarray, k: int, seed: int = 0, sample: int = 100_000) -> np.ndarray:
    """k-means++ in CIELAB on a pixel subsample. Returns (k, 3) cluster centres."""
    X = lab.reshape(-1, 3)
    if len(X) > sample:
        X = X[np.random.default_rng(seed).choice(len(X), sample, replace=False)]
    return KMeans(k, init="k-means++", n_init=4, random_state=seed).fit(X).cluster_centers_


def kmeans_potts(
    rgb: np.ndarray,
    k: int = 16,
    lam: float = 2.0,
    min_area: int = 120,
    min_radius: float = 4.0,
    smooth_iters: int = 3,
    **_,
) -> Result:
    t = {}
    t0 = time.perf_counter()
    sm = smooth(rgb, smooth_iters)
    lab = rgb2lab(sm)
    t["smooth"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    palette = kmeans_palette(lab, k)
    t["kmeans"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    labels = potts_labels(lab, palette, lam=lam)
    t["potts"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    labels = clean_regions(labels, palette, min_area, min_radius)
    t["cleanup"] = time.perf_counter() - t0
    return finalize("kmeans-potts", labels, lab, rgb, sm, t)


def ward_merge(seg: np.ndarray, lab: np.ndarray, n_target: int) -> np.ndarray:
    """Agglomerative merging of adjacent segments until `n_target` remain.

    Merge cost is the Ward criterion  n_a n_b / (n_a + n_b) * |mu_a - mu_b|^2, i.e. the
    increase in colour variance, so small or very similar neighbours merge first.
    """
    S = int(seg.max()) + 1
    flat = seg.ravel()
    n = np.bincount(flat, minlength=S).astype(np.float64)
    mu = np.stack([np.bincount(flat, weights=lab[..., c].ravel(), minlength=S) for c in range(3)], axis=1)
    mu /= np.maximum(n, 1)[:, None]

    nbrs: list[set[int]] = [set() for _ in range(S)]
    lo, hi, _ = adjacency(seg, S - 1)
    for a, b in zip(lo.tolist(), hi.tolist()):
        nbrs[a].add(b)
        nbrs[b].add(a)

    def cost(a, b):
        d = mu[a] - mu[b]
        return n[a] * n[b] / (n[a] + n[b]) * float(d @ d)

    version = np.zeros(S, np.int64)
    alive = np.ones(S, bool)
    heap = [(cost(a, b), a, b, 0, 0) for a in range(S) for b in nbrs[a] if a < b]
    heapq.heapify(heap)
    parent = np.arange(S)
    remaining = S
    while remaining > n_target and heap:
        _, a, b, va, vb = heapq.heappop(heap)
        if not (alive[a] and alive[b]) or version[a] != va or version[b] != vb:
            continue
        mu[a] = (mu[a] * n[a] + mu[b] * n[b]) / (n[a] + n[b])
        n[a] += n[b]
        alive[b] = False
        parent[b] = a
        nbrs[a] |= nbrs[b]
        nbrs[a].discard(a)
        nbrs[a].discard(b)
        for x in nbrs[b]:
            nbrs[x].discard(b)
            if x != a:
                nbrs[x].add(a)
        version[a] += 1
        remaining -= 1
        for x in nbrs[a]:
            heapq.heappush(heap, (cost(a, x), min(a, x), max(a, x), version[min(a, x)], version[max(a, x)]))

    root = np.arange(S)
    for i in range(S):  # resolve union-find chains (parents always point to smaller-or-equal merge roots)
        r = i
        while parent[r] != r:
            r = parent[r]
        root[i] = r
    _, compact = np.unique(root, return_inverse=True)
    return compact[seg]


def slic_merge(
    rgb: np.ndarray,
    k: int = 16,
    regions: int = 300,
    superpixels: int = 4000,
    compactness: float = 0.05,  # Lab-scale input: values >= ~1 degenerate into a square grid
    min_area: int = 120,
    min_radius: float = 4.0,
    smooth_iters: int = 2,
    **_,
) -> Result:
    t = {}
    t0 = time.perf_counter()
    sm = smooth(rgb, smooth_iters)
    lab = rgb2lab(sm)
    t["smooth"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    seg = slic(lab, n_segments=superpixels, compactness=compactness, sigma=1,
               convert2lab=False, start_label=0, enforce_connectivity=True, channel_axis=-1)
    t["slic"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    seg = ward_merge(seg, lab, regions)
    t["merge"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    R = int(seg.max()) + 1
    area = np.bincount(seg.ravel(), minlength=R).astype(np.float64)
    mean = np.stack([np.bincount(seg.ravel(), weights=lab[..., c].ravel(), minlength=R) / area for c in range(3)], 1)
    kk = min(k, R)
    km = KMeans(kk, init="k-means++", n_init=4, random_state=0).fit(mean, sample_weight=area)
    labels = km.labels_[seg].astype(np.int32)
    t["palette"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    labels = clean_regions(labels, km.cluster_centers_, min_area, min_radius)
    t["cleanup"] = time.perf_counter() - t0
    return finalize("slic-merge", labels, lab, rgb, sm, t)


METHODS = {"kmeans-potts": kmeans_potts, "slic-merge": slic_merge}


def run_method(name: str, rgb: np.ndarray, **opts) -> Result:
    return METHODS[name](rgb, **opts)
