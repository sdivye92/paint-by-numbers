import io
import json
import zipfile
from pathlib import Path

import pytest

from pbn.backend.imageops import load_image
from pbn.backend.methods import run_method
from pbn.backend.package import build_package, make_zip, package_filenames, safe_name
from pbn.backend.recipes import build_recipes
from pbn.backend.render import ARTIFACTS, RECIPE_ARTIFACTS

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "coffee.jpg"


@pytest.fixture(scope="module")
def result():
    return run_method("slic-merge", load_image(SAMPLE, 300), k=6, regions=40, superpixels=400)


def test_safe_name_removes_paths_and_odd_characters():
    assert safe_name("my photo_v2") == "my photo_v2"
    assert "/" not in safe_name("../../etc/passwd") and ".." not in safe_name("../../etc/passwd")
    assert safe_name("a/b\\c:d*e?") == "a_b_c_d_e"
    assert safe_name("   ") == "paint_by_numbers" and safe_name("///") == "paint_by_numbers"


def test_package_contains_only_the_chosen_files_in_one_folder(result):
    data, names = build_package(result, "my pack", artifacts=["svg", "json"], info={"hello": "world"})
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.testzip() is None
    assert sorted(zf.namelist()) == sorted(names) == sorted(
        ["my pack/my pack_outline.svg", "my pack/my pack_palette.json", "my pack/package_info.json"])
    assert json.loads(zf.read("my pack/package_info.json")) == {"hello": "world"}
    assert zf.read("my pack/my pack_outline.svg").startswith(b"<svg")


def test_package_without_info_and_with_recipes(result):
    recipes = build_recipes(result)
    data, names = build_package(result, "x", ARTIFACTS + RECIPE_ARTIFACTS, scale=2, recipes=recipes)
    assert len(names) == 8 and not any(n.endswith("package_info.json") for n in names)
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.read("x/x_recipes.csv").startswith(b"number,target_hex")


def test_recipe_artifacts_need_recipes(result):
    with pytest.raises(ValueError):
        build_package(result, "x", ["recipes_csv"])


def test_unsafe_names_cannot_escape_the_archive(result):
    data, names = build_package(result, "../../evil", artifacts=["json"])
    assert all(".." not in n and n.count("/") == 1 for n in names)


def test_make_zip_round_trip(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hi")
    zf = zipfile.ZipFile(io.BytesIO(make_zip({"a": f}, "root")))
    assert zf.read("root/a.txt") == b"hi"


def test_planned_file_names_match_the_built_package(result):
    recipes = build_recipes(result)
    everything = ARTIFACTS + RECIPE_ARTIFACTS
    for chosen, with_info in ((everything, True), (["svg", "json"], True), (["preview"], False)):
        info = {"k": 1} if with_info else None
        _, built = build_package(result, "my pack", chosen, recipes=recipes, info=info)
        assert package_filenames("my pack", chosen, with_info) == built  # same names, same order
