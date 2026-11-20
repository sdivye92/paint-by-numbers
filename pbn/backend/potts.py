"""Potts-model label assignment solved with graph-cut alpha-expansion.

Energy:  E(l) = sum_p D_p(l_p)  +  sum_{pq} w_pq * [l_p != l_q]

D_p is the squared CIELAB distance from pixel p to palette entry l_p, so with
lam = 0 this is exactly the k-means assignment. The pairwise term penalises label
changes between neighbours, and w_pq shrinks where the image has a real edge
(contrast-sensitive), so noise gets smoothed away but object boundaries survive.
"""
from __future__ import annotations

import maxflow
import numpy as np

_RIGHT = np.array([[0, 0, 0], [0, 0, 1], [0, 0, 0]])
_DOWN = np.array([[0, 0, 0], [0, 0, 0], [0, 1, 0]])


def pair_weights(lab: np.ndarray, lam: float, edge_sigma: float, floor: float):
    """Contrast-sensitive Potts weights for horizontal (H,W-1) and vertical (H-1,W) neighbours."""

    def f(d):
        return (lam * (floor + (1 - floor) * np.exp(-((d / edge_sigma) ** 2)))).astype(np.float64)

    dh = np.linalg.norm(lab[:, 1:] - lab[:, :-1], axis=2)
    dv = np.linalg.norm(lab[1:] - lab[:-1], axis=2)
    return f(dh), f(dv)


def data_costs(lab: np.ndarray, palette: np.ndarray, data_scale: float) -> np.ndarray:
    H, W, _ = lab.shape
    data = np.empty((H, W, len(palette)), np.float32)
    for k, c in enumerate(palette):
        data[:, :, k] = ((lab - c) ** 2).sum(2) / data_scale**2
    return data


def energy(labels: np.ndarray, data: np.ndarray, wh: np.ndarray, wv: np.ndarray) -> float:
    e = np.take_along_axis(data, labels[..., None], 2).sum(dtype=np.float64)
    e += (wh * (labels[:, 1:] != labels[:, :-1])).sum()
    e += (wv * (labels[1:] != labels[:-1])).sum()
    return float(e)


def expand(cur: np.ndarray, alpha: int, data: np.ndarray, wh: np.ndarray, wv: np.ndarray) -> np.ndarray:
    """One alpha-expansion move: every pixel either keeps its label or switches to `alpha`.

    Binary variable x_p (0 = keep, 1 = switch). For each neighbouring pair the four
    costs E00, E01, E10, E11 are decomposed as
        E(a, b) = E00 + (E10-E00) a + (E11-E10) b + (E01+E10-E00-E11) (1-a) b
    which is a unary part plus one non-negative directed edge, because Potts is a
    metric (so E01 + E10 >= E00 + E11).
    """
    H, W = cur.shape
    u0 = np.take_along_axis(data, cur[..., None], 2)[..., 0].astype(np.float64)
    u1 = data[:, :, alpha].astype(np.float64)

    g = maxflow.Graph[float]()
    ids = g.add_grid_nodes((H, W))

    for p, q, w, structure, sl_p, sl_q in (
        (cur[:, :-1], cur[:, 1:], wh, _RIGHT, np.s_[:, :-1], np.s_[:, 1:]),
        (cur[:-1], cur[1:], wv, _DOWN, np.s_[:-1, :], np.s_[1:, :]),
    ):
        e00 = w * (p != q)
        e01 = w * (p != alpha)  # p keeps its label, q -> alpha
        e10 = w * (q != alpha)  # p -> alpha, q keeps its label
        u1[sl_p] += e10 - e00
        u1[sl_q] += -e10  # (E11 - E10) with E11 = 0
        cap = np.zeros((H, W))
        cap[sl_p] = np.maximum(e01 + e10 - e00, 0.0)
        g.add_grid_edges(ids, cap, structure=structure, symmetric=False)

    m = np.minimum(u0, u1)  # shift so terminal capacities are non-negative
    g.add_grid_tedges(ids, u1 - m, u0 - m)  # (source cap: paid if x=1, sink cap: paid if x=0)
    g.maxflow()
    switch = g.get_grid_segments(ids)  # True = sink side = x=1
    return np.where(switch, alpha, cur).astype(cur.dtype)


def potts_labels(
    lab: np.ndarray,
    palette: np.ndarray,
    lam: float = 2.0,
    data_scale: float = 10.0,
    edge_sigma: float = 8.0,
    floor: float = 0.2,
    sweeps: int = 3,
    seed: int = 0,
) -> np.ndarray:
    """Assign each pixel a palette index by minimising the Potts energy."""
    H, W, _ = lab.shape
    data = data_costs(lab, palette, data_scale)
    labels = data.argmin(2).astype(np.int32)
    if lam <= 0:
        return labels
    wh, wv = pair_weights(lab, lam, edge_sigma, floor)
    rng = np.random.default_rng(seed)
    for _ in range(sweeps):
        changed = 0
        for alpha in rng.permutation(len(palette)):
            new = expand(labels, int(alpha), data, wh, wv)
            changed += int((new != labels).sum())
            labels = new
        if changed < 0.001 * H * W:
            break
    return labels
