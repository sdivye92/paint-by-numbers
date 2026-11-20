from pathlib import Path

import numpy as np
import pytest

from pbn.backend.imageops import load_image
from pbn.backend.methods import run_method
from pbn.backend.paints import STANDARD_SET, build_library, match, mix_rgb
from pbn.backend.recipes import build_recipes, usage_summary
from pbn.backend.render import ARTIFACTS, RECIPE_ARTIFACTS, save_all

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "coffee.jpg"
IDX = {p.name: i for i, p in enumerate(STANDARD_SET)}


def mix(**parts):
    w = np.zeros(len(STANDARD_SET))
    for name, v in parts.items():
        w[IDX[name.replace("_", " ")]] = v
    return mix_rgb(STANDARD_SET, w)


def test_single_paint_returns_its_own_colour():
    for p in STANDARD_SET:
        got = mix_rgb(STANDARD_SET, np.eye(len(STANDARD_SET))[IDX[p.name]])
        assert np.abs(got - np.array(p.rgb)).max() < 8, p.name


def test_subtractive_mixing_behaves_like_paint():
    grey = mix(Titanium_White=1, Mars_Black=1)
    assert 40 < grey.mean() < 160 and grey.max() - grey.min() < 12  # neutral mid/dark grey

    greens = [mix(Cadmium_Yellow_Light=r, Ultramarine_Blue=1) for r in (1, 2, 4, 8)]
    assert any(g[1] > g[0] and g[1] > g[2] for g in greens)  # yellow + blue goes green, not grey

    pink = mix(Cadmium_Red_Medium=1, Titanium_White=3)
    red = mix(Cadmium_Red_Medium=1)
    assert pink.mean() > red.mean() and pink[0] > pink[1] > 0  # lighter, still red-leaning

    assert mix(Phthalo_Blue=1, Titanium_White=20).mean() > mix(Phthalo_Blue=1, Titanium_White=4).mean()


def test_library_recipes_are_reduced_and_bounded():
    lib = build_library(STANDARD_SET, 3)
    assert lib.n_used.max() <= 3
    multi = lib.parts[lib.n_used > 1]
    assert np.gcd.reduce(multi, axis=1).max() == 1  # no duplicate ratios like 2:4


def test_each_tube_matches_itself():
    lib = build_library(STANDARD_SET, 3)
    from pbn.backend.imageops import rgb2lab

    for p in STANDARD_SET:
        lab = rgb2lab(np.array(p.rgb, np.uint8).reshape(1, 1, 3)).reshape(3)
        _, de = match(lib, lab)
        assert de < 1.5, (p.name, de)


@pytest.fixture(scope="module")
def result():
    return run_method("slic-merge", load_image(SAMPLE, 300), k=6, regions=40, superpixels=400)


def test_quantities_add_up(result):
    recipes = build_recipes(result, canvas_cm=(30, 40), ml_per_100cm2=2.0, coats=2, margin=0.25)
    assert len(recipes) == result.k
    for r in recipes:
        assert abs(sum(ml for _, ml in r.ml) - r.total_ml) < 1e-9
        assert r.parts == sorted(r.parts, key=lambda t: -t[1])
    expected = 30 * 40 / 100 * 2.0 * 2 * 1.25  # coverages sum to 1
    assert abs(sum(r.total_ml for r in recipes) - expected) < 1e-6
    assert abs(sum(usage_summary(recipes).values()) - expected) < 1e-6


def test_fewer_paints_option_is_respected(result):
    two = build_recipes(result, max_paints=2)
    assert all(len(r.parts) <= 2 for r in two)


def test_recipe_artifacts(tmp_path, result):
    recipes = build_recipes(result)
    paths = save_all(result, tmp_path, "x", artifacts=ARTIFACTS + RECIPE_ARTIFACTS, recipes=recipes)
    assert {"recipes_png", "recipes_csv", "mix_preview", "json"} <= set(paths)
    assert (tmp_path / "x_mix_preview.png").exists()
    assert (tmp_path / "x_recipes.csv").read_text().startswith("number,target_hex")
    assert "recipe" in (tmp_path / "x_palette.json").read_text()
    with pytest.raises(ValueError):
        save_all(result, tmp_path, "y", artifacts=["recipes_csv"])  # no recipes given


def test_refine_is_never_worse_than_the_library_and_respects_the_tube_limit(result):
    from pbn.backend.paints import LADDER, _score_recipes, refine

    lib = build_library(STANDARD_SET, 4)
    for lab in result.palette_lab:
        idx, _ = match(lib, lab)
        base, _, _ = _score_recipes(STANDARD_SET, lib.parts[idx], lab, 1.0, 0.3)
        parts, de, rgb = refine(lib, lab, max_paints=6)
        got, got_de, _ = _score_recipes(STANDARD_SET, parts, lab, 1.0, 0.3)
        assert got[0] <= base[0] + 1e-6  # same objective, starts from the library optimum
        assert 1 <= (parts > 0).sum() <= 6
        assert abs(de - got_de[0]) < 1e-6 and len(rgb) == 3


def test_five_and_six_tube_recipes_through_build_recipes(result):
    for limit in (5, 6):
        recipes = build_recipes(result, max_paints=limit)
        assert len(recipes) == result.k
        assert all(1 <= len(r.parts) <= limit for r in recipes)
    four = build_recipes(result, max_paints=4)
    six = build_recipes(result, max_paints=6)
    # the extra freedom can only lower (or keep) the combined score, never raise it
    assert sum(r.delta_e + 1.0 * (len(r.parts) - 1) + 0.3 * np.log2(sum(p for _, p in r.parts)) for r in six) <= \
           sum(r.delta_e + 1.0 * (len(r.parts) - 1) + 0.3 * np.log2(sum(p for _, p in r.parts)) for r in four) + 1e-6


def test_lower_tube_penalty_uses_more_tubes(result):
    simple = build_recipes(result, max_paints=6, tube_penalty=1.0)
    accurate = build_recipes(result, max_paints=6, tube_penalty=0.1)
    assert np.mean([len(r.parts) for r in accurate]) >= np.mean([len(r.parts) for r in simple])
    assert all(len(r.parts) <= 6 for r in accurate)


def test_mix_preview_uses_the_predicted_mix_colours(result):
    from pbn.backend.recipes import mix_preview_image, preview_error

    recipes = build_recipes(result)
    img = mix_preview_image(result, recipes)
    assert img.shape == result.labels.shape + (3,) and img.dtype == np.uint8
    for r in recipes[:4]:  # every pixel of region-colour i carries recipe i's predicted mix
        assert (img[result.labels == r.number - 1] == np.array(r.mix_rgb)).all()
    assert preview_error(result.original_rgb, result.original_rgb) == 0.0
    err_algo = preview_error(result.original_rgb, result.palette_rgb[result.labels])
    err_mix = preview_error(result.original_rgb, img)
    assert 0 < err_algo < 40 and 0 < err_mix < 40  # sane magnitudes (mean dE76 per pixel)
