"""Headless UI test of the Streamlit app using Streamlit's AppTest."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "pbn" / "frontend" / "app.py"
SAMPLE = ROOT / "samples" / "coffee.jpg"


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample image missing")
def test_compare_generate_and_export(tmp_path):
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception
    assert any("Upload a photo" in i.value for i in at.sidebar.info)  # nothing chosen yet

    at.sidebar.selectbox[0].select(SAMPLE).run()
    assert not at.exception

    # Compare tab: shrink the work so the test is quick, then run both methods.
    at.slider(key="cmp_low_size").set_value(400)
    at.button(key="cmp_run").click().run()
    assert not at.exception
    assert any("Metrics" in s.value for s in at.subheader)

    # Generate tab + export to a chosen folder.
    at.slider(key="gen_low_size").set_value(400)
    at.button(key="gen_run").click().run()
    assert not at.exception
    assert any("Export" in s.value for s in at.subheader)
    assert any("Paint recipes" in s.value for s in at.subheader)
    assert any("Photo vs template vs your paints" in s.value for s in at.subheader)
    at.select_slider(key="max_paints").set_value(6).run()  # 5-6 tube search
    at.select_slider(key="recipe_style").set_value("Accurate").run()
    assert not at.exception

    at.text_input(key="export_dir").set_value(str(tmp_path / "exports")).run()
    export = next(b for b in at.button if b.label == "Export")
    export.click().run()
    assert not at.exception
    written = sorted(p.name for p in (tmp_path / "exports").iterdir())
    assert any(n.endswith("_outline.svg") for n in written)
    assert any(n.endswith("_palette.json") for n in written)
    assert len(written) == 8  # 5 template files + recipe sheet + recipe CSV + mixed-colour preview


def test_export_subset(tmp_path):
    from pbn.backend.imageops import load_image
    from pbn.backend.methods import run_method
    from pbn.backend.render import save_all

    res = run_method("slic-merge", load_image(SAMPLE, 300), k=6, regions=40, superpixels=400)
    paths = save_all(res, tmp_path, "x", artifacts=["svg", "json"])
    assert set(paths) == {"svg", "json"}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x_outline.svg", "x_palette.json"]
    with pytest.raises(ValueError):
        save_all(res, tmp_path, "x", artifacts=["nope"])
