import itertools

import numpy as np

from pbn.backend.potts import data_costs, energy, expand, pair_weights, potts_labels


def _tiny_problem(seed):
    rng = np.random.default_rng(seed)
    lab = rng.normal(size=(3, 3, 3)).astype(np.float32) * 12 + 50
    palette = rng.normal(size=(3, 3)).astype(np.float32) * 12 + 50
    return lab, palette


def test_expand_is_optimal_binary_move():
    """The graph-cut move must equal the best of all 2^9 keep/switch combinations."""
    for seed in range(8):
        lab, palette = _tiny_problem(seed)
        data = data_costs(lab, palette, 10.0)
        wh, wv = pair_weights(lab, 2.0, 8.0, 0.2)
        cur = np.random.default_rng(seed + 100).integers(0, 3, size=(3, 3)).astype(np.int32)
        alpha = seed % 3

        best = min(
            energy(np.where(np.array(mask).reshape(3, 3), alpha, cur), data, wh, wv)
            for mask in itertools.product([0, 1], repeat=9)
        )
        got = energy(expand(cur, alpha, data, wh, wv), data, wh, wv)
        assert abs(got - best) < 1e-4, (seed, got, best)


def test_energy_never_increases_and_smoothing_removes_speckle():
    rng = np.random.default_rng(0)
    lab = np.zeros((40, 40, 3), np.float32)
    lab[:, :20] = (30, 0, 0)
    lab[:, 20:] = (80, 0, 0)
    lab += rng.normal(scale=6, size=lab.shape).astype(np.float32)
    palette = np.array([[30, 0, 0], [80, 0, 0]], np.float32)

    raw = potts_labels(lab, palette, lam=0)
    smooth = potts_labels(lab, palette, lam=2.0)
    data = data_costs(lab, palette, 10.0)
    wh, wv = pair_weights(lab, 2.0, 8.0, 0.2)
    assert energy(smooth, data, wh, wv) <= energy(raw, data, wh, wv) + 1e-6
    truth = np.zeros((40, 40), int)
    truth[:, 20:] = 1
    assert (smooth != truth).sum() <= (raw != truth).sum()
