import numpy as np
import pytest

from pbn.backend.methods import METHODS, run_method
from pbn.backend.regions import connected_components, region_geometry
from pbn.backend.render import trace_chains


def _synthetic(seed=0, size=120):
    """Four flat colour blocks plus noise and a few 1-px specks."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3), np.float32)
    half = size // 2
    img[:half, :half] = (200, 60, 60)
    img[:half, half:] = (60, 200, 60)
    img[half:, :half] = (60, 60, 200)
    img[half:, half:] = (230, 230, 80)
    img += rng.normal(scale=12, size=img.shape)
    for _ in range(40):
        y, x = rng.integers(0, size, 2)
        img[y, x] = (0, 0, 0)
    return np.clip(img, 0, 255).astype(np.uint8)


@pytest.mark.parametrize("method", list(METHODS))
def test_regions_are_paintable(method):
    res = run_method(method, _synthetic(), k=4, min_area=80, min_radius=3.0, regions=30, superpixels=300)
    cc, n = connected_components(res.labels)
    area, radius, _ = region_geometry(cc, n)
    assert area.min() >= 80
    assert radius.min() >= 3.0
    assert res.k <= 4
    assert n <= 8  # 4 blocks, allowing for a couple of leftover pieces


@pytest.mark.parametrize("method", list(METHODS))
def test_palette_numbers_are_dark_to_light(method):
    res = run_method(method, _synthetic(), k=4, regions=30, superpixels=300)
    assert np.all(np.diff(res.palette_lab[:, 0]) >= 0)


def test_chains_cover_every_region_boundary_once():
    labels = np.zeros((10, 10), np.int32)
    labels[:, 5:] = 1
    labels[5:, :5] = 2
    chains = trace_chains(labels)
    # every chain endpoint lies on a junction or the page border; total length equals
    # the boundary-edge count (image border 40 + interior 10 + 5 = 55) up to smoothing
    total = sum(np.hypot(*np.diff(p, axis=0).T).sum() for p, _ in chains)
    assert 50 <= total <= 56
