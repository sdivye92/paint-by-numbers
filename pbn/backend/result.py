from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .imageops import lab2rgb


@dataclass
class Result:
    name: str
    labels: np.ndarray  # (H, W) palette index; paint number = index + 1
    palette_lab: np.ndarray  # (K, 3)
    palette_rgb: np.ndarray  # (K, 3) uint8
    original_rgb: np.ndarray
    smoothed_rgb: np.ndarray
    timings: dict = field(default_factory=dict)

    @property
    def k(self) -> int:
        return len(self.palette_rgb)


def finalize(name, labels, lab, original_rgb, smoothed_rgb, timings) -> Result:
    """Drop unused colours, set each colour to the mean of the pixels it ended up covering,
    and number colours dark -> light."""
    used = np.unique(labels)
    remap = np.full(labels.max() + 1, -1, np.int64)
    remap[used] = np.arange(len(used))
    labels = remap[labels]

    counts = np.bincount(labels.ravel(), minlength=len(used)).astype(np.float64)
    pal = np.stack(
        [np.bincount(labels.ravel(), weights=lab[..., c].ravel(), minlength=len(used)) / counts for c in range(3)],
        axis=1,
    )
    order = np.argsort(pal[:, 0])
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    pal = pal[order]
    return Result(name, rank[labels].astype(np.int32), pal, lab2rgb(pal), original_rgb, smoothed_rgb, timings)
