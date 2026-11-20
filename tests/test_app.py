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

    # Generate tab: results, paint recipes, three-way comparison and the download section.
    at.slider(key="gen_low_size").set_value(400)
    at.button(key="gen_run").click().run()
    assert not at.exception
    assert any("Paint recipes" in s.value for s in at.subheader)
    assert any("Photo vs template vs your paints" in s.value for s in at.subheader)
    at.select_slider(key="max_paints").set_value(6).run()  # 5-6 tube search
    at.select_slider(key="recipe_style").set_value("Accurate").run()
    assert not at.exception

    # The download button builds the ZIP only when clicked (deferred), so here we check it is offered and
    # that it disables itself when nothing is selected. The ZIP contents are covered in test_package.py.
    assert any("Download" in s.value for s in at.subheader)
    (button,) = at.get("download_button")
    assert button.proto.label == "Download ZIP" and not button.proto.disabled
    assert any("never on the server" in c.value for c in at.caption)
    at.multiselect[0].set_value([]).run()
    assert not at.exception
    assert at.get("download_button")[0].proto.disabled



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
