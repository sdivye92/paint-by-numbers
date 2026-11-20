"""Connected regions, adjacency, geometry and the min-area / min-width cleanup."""
from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage
from scipy.spatial.distance import cdist


def connected_components(labels: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected components of each palette label. Returns (cc map with ids 1..n, n)."""
    cc = np.zeros(labels.shape, np.int32)
    n = 0
    for lab in np.unique(labels):
        num, comp = cv2.connectedComponents((labels == lab).astype(np.uint8), connectivity=4)
        m = comp > 0
        cc[m] = comp[m] + n
        n += num - 1
    return cc, n


def adjacency(ids: np.ndarray, n: int | None = None):
    """Adjacent id pairs (lo, hi) and the length of their shared boundary (in pixel edges)."""
    if n is None:
        n = int(ids.max())
    a = np.concatenate([ids[:, :-1].ravel(), ids[:-1, :].ravel()]).astype(np.int64)
    b = np.concatenate([ids[:, 1:].ravel(), ids[1:, :].ravel()]).astype(np.int64)
    m = a != b
    a, b = a[m], b[m]
    key = np.minimum(a, b) * (n + 1) + np.maximum(a, b)
    uniq, counts = np.unique(key, return_counts=True)
    return uniq // (n + 1), uniq % (n + 1), counts


def region_geometry(cc: np.ndarray, n: int):
    """Per-region (area, inscribed-circle radius, pole-of-inaccessibility (y, x)).

    One distance transform from all region boundaries gives, for every pixel, the
    distance to the edge of its own region; its per-region maximum is the radius of
    the largest circle that fits, which is both the "can a brush fit here" test and
    the best place to put the region's number.
    """
    index = np.arange(1, n + 1)
    area = np.bincount(cc.ravel(), minlength=n + 1)[1:]
    edge = np.zeros(cc.shape, bool)
    dx = cc[:, 1:] != cc[:, :-1]
    edge[:, 1:] |= dx
    edge[:, :-1] |= dx
    dy = cc[1:] != cc[:-1]
    edge[1:] |= dy
    edge[:-1] |= dy
    inside = np.pad(~edge, 1).astype(np.uint8)  # padding = image border counts as an edge
    dt = cv2.distanceTransform(inside, cv2.DIST_L2, 5)[1:-1, 1:-1]
    radius = np.asarray(ndimage.maximum(dt, cc, index)) + 0.5
    pos = np.asarray(ndimage.maximum_position(dt, cc, index))
    return area, radius, pos


def clean_regions(
    labels: np.ndarray,
    palette_lab: np.ndarray,
    min_area: int,
    min_radius: float,
    max_passes: int = 30,
) -> np.ndarray:
    """Repaint regions that are too small or too thin to paint.

    Each offending region (smallest first) takes the palette colour of the neighbour
    it is closest to in CIELAB (weighted towards the neighbour it shares most border
    with). Repeats until every connected region has area >= min_area and an
    inscribed radius >= min_radius.
    """
    labels = labels.copy()
    de = cdist(palette_lab, palette_lab)
    for _ in range(max_passes):
        cc, n = connected_components(labels)
        area, radius, _ = region_geometry(cc, n)
        bad = np.flatnonzero((area < min_area) | (radius < min_radius)) + 1
        if bad.size == 0:
            break
        region_label = np.zeros(n + 1, np.int64)
        region_label[cc.ravel()] = labels.ravel()
        lo, hi, cnt = adjacency(cc, n)
        nbrs: list[dict[int, int]] = [dict() for _ in range(n + 1)]
        for a, b, c in zip(lo.tolist(), hi.tolist(), cnt.tolist()):
            nbrs[a][b] = c
            nbrs[b][a] = c
        changed = False
        for r in bad[np.argsort(area[bad - 1], kind="stable")]:
            adj = nbrs[r]
            if not adj:
                continue
            total = sum(adj.values())
            mine = region_label[r]
            best, best_cost = None, np.inf
            for q, c in adj.items():
                other = region_label[q]
                if other == mine:
                    continue
                cost = de[mine, other] * (1.5 - c / total)
                if cost < best_cost:
                    best, best_cost = other, cost
            if best is not None:
                region_label[r] = best
                changed = True
        labels = region_label[cc]
        if not changed:
            break
    return labels
