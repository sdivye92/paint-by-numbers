"""Streamlit front end:  streamlit run pbn/frontend/app.py   (or: python -m pbn app)"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # make `pbn` importable however the script is launched
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from pbn.backend.methods import METHODS
from pbn.backend.render import ARTIFACTS, RECIPE_ARTIFACTS, save_all
from pbn.frontend.folder_picker import pick_folder
from pbn.frontend.hero import hero_html
from pbn.frontend.paints_ui import mix_comparison, paints_section
from pbn.frontend.params import param_form
from pbn.frontend.style import GLOBAL_CSS
from pbn.frontend.views import METHOD_LABELS, freeze, run_view

st.set_page_config(page_title="Paint by Numbers", page_icon=":material/brush:", layout="wide")

ARTIFACT_LABELS = {
    "preview": "Colour preview (PNG)",
    "outline": "Numbered outline (PNG)",
    "svg": "Numbered outline (SVG, vector)",
    "legend": "Colour legend (PNG)",
    "json": "Palette data (JSON)",
    "recipes_png": "Paint recipe sheet (PNG)",
    "recipes_csv": "Paint recipes (CSV)",
    "mix_preview": "Mixed-colour preview (PNG)",
}
METRIC_LABELS = {
    "colors": "Colours", "regions": "Regions", "median_area": "Median region area (px)",
    "min_area": "Smallest region (px)", "min_radius": "Smallest radius (px)",
    "mean_dE": "Mean colour error (ΔE)", "seconds": "Time (s)",
}


# ------------------------------------------------------------------ image source
def choose_image():
    samples = sorted(p for p in (ROOT / "samples").glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    with st.sidebar:
        st.header("Image")
        upload = st.file_uploader("Upload a photo", type=["jpg", "jpeg", "png", "webp", "bmp"])
        sample = None
        if samples:
            sample = st.selectbox("…or use a sample", [None, *samples], format_func=lambda p: "—" if p is None else p.name)
        if upload is not None:
            data, name = upload.getvalue(), Path(upload.name).stem
        elif sample is not None:
            data, name = sample.read_bytes(), sample.stem
        else:
            st.info("Upload a photo or pick a sample to begin.")
            return None, None
        st.image(data, caption=name, width="stretch")
        st.caption("Set parameters and run in either tab. Results stay until you run again.")
    return data, name


def run_methods(data: bytes, methods, params: dict) -> dict:
    views = {}
    for m in methods:
        with st.spinner(f"Running {METHOD_LABELS[m]}…"):
            views[m] = run_view(data, m, m_params(params, m))
    return views


def m_params(params: dict, method: str) -> tuple:
    """Params that matter for `method`, so unrelated sliders don't invalidate its cache."""
    p = {k: v for k, v in params.items() if k != "detail"}
    if method == "kmeans-potts":
        p.update(regions=0, superpixels=0, compactness=0.0)
    else:
        p["lam"] = 0.0
    return freeze(p)


# ------------------------------------------------------------------ compare tab
def compare_tab(data: bytes, name: str):
    left, right = st.columns([1, 3], gap="large")
    with left:
        st.subheader("Settings")
        st.caption("Both methods run on the same image with the same settings.")
        params = param_form("cmp")
        if st.button("Run comparison", type="primary", key="cmp_run", width="stretch"):
            st.session_state.cmp = dict(name=name, data=data, params=params)
    with right:
        snap = st.session_state.get("cmp")
        if not snap:
            st.info("Choose settings on the left and press **Run comparison**.")
            return
        if snap["name"] != name or snap["params"] != params:
            st.info("Image or parameters changed since the last run — press **Run comparison** to refresh. "
                    "What's shown is still the previous run.")
        show_comparison(snap)


def show_comparison(snap: dict):
    views = run_methods(snap["data"], METHODS, snap["params"])

    head = st.columns([1, 2], gap="large")
    head[0].subheader("Original")
    head[0].image(next(iter(views.values())).result.original_rgb, width="stretch")
    table = pd.DataFrame(
        {METHOD_LABELS[m]: {METRIC_LABELS[k]: v.metrics[k] for k in METRIC_LABELS} for m, v in views.items()}
    )
    head[1].subheader("Metrics")
    head[1].dataframe(table.astype(str), width="stretch")
    head[1].caption("Lower mean ΔE = closer to the photo. Fewer, larger regions = easier to paint.")

    previews = st.columns(2, gap="large")
    for col, (m, v) in zip(previews, views.items()):
        col.subheader(METHOD_LABELS[m])
        col.image(v.preview, caption="Colour preview", width="stretch")
    outlines = st.columns(2, gap="large")
    for col, v in zip(outlines, views.values()):
        col.image(v.outline, caption="Numbered outline (use fullscreen to read the numbers)", width="stretch")


# ------------------------------------------------------------------ generate tab
def _browse():
    chosen = pick_folder(st.session_state.export_dir)
    if chosen:
        st.session_state.export_dir = chosen
        st.session_state.browse_note = None
    else:
        st.session_state.browse_note = "No folder chosen (dialog cancelled or unavailable) — type the path instead."


def generate_tab(data: bytes, name: str):
    left, right = st.columns([1, 3], gap="large")
    with left:
        st.subheader("Settings")
        method = st.radio("Method", list(METHODS), format_func=METHOD_LABELS.get, key="gen_method")
        params = param_form("gen", method)
        scale = st.slider("Output scale", 1, 4, 3, key="gen_scale",
                          help="Size multiplier for the exported outline PNG and SVG (display size only for the SVG; it stays vector).")
        if st.button("Generate", type="primary", key="gen_run", width="stretch"):
            st.session_state.gen = dict(name=name, data=data, method=method, params=params, scale=scale)

    with right:
        snap = st.session_state.get("gen")
        if not snap:
            st.info("Choose settings on the left and press **Generate**.")
            return
        if (snap["name"], snap["method"], snap["params"]) != (name, method, params):
            st.info("Image or settings changed since the last run — press **Generate** to refresh. "
                    "What's shown (and exported) is still the previous run.")
        view = run_methods(snap["data"], [snap["method"]], snap["params"])[snap["method"]]

        cols = st.columns(4)
        cols[0].metric("Colours", view.metrics["colors"])
        cols[1].metric("Regions", view.metrics["regions"])
        cols[2].metric("Mean colour error (ΔE)", view.metrics["mean_dE"])
        cols[3].metric("Time (s)", view.metrics["seconds"])

        a, b = st.columns(2)
        a.subheader("Colour preview")
        a.image(view.preview, width="stretch")
        b.subheader("Numbered outline")
        b.image(view.outline, width="stretch")
        st.caption("Hover an image and use the fullscreen icon to inspect the numbers.")
        st.subheader("Legend")
        st.image(view.legend)

        st.divider()
        recipes = paints_section(view.result)
        if recipes:
            st.divider()
            mix_comparison(view, recipes)

        st.divider()
        export_section(snap, view, recipes)


def export_section(snap: dict, view, recipes=None):
    st.subheader("Export")
    st.session_state.setdefault("export_dir", str(Path.home() / "pbn_exports"))
    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    c1.text_input("Export folder", key="export_dir", help="Created if it doesn't exist. This is a folder on the machine running the app.")
    c2.button("Browse…", on_click=_browse, width="stretch")
    if st.session_state.get("browse_note"):
        st.caption(st.session_state.browse_note)
    options = list(ARTIFACTS) + (list(RECIPE_ARTIFACTS) if recipes else [])
    chosen = st.multiselect("Artifacts", options, default=options, format_func=ARTIFACT_LABELS.get)
    stem = st.text_input("File name prefix", value=f"{snap['name']}_{snap['method']}", key=f"stem_{snap['name']}_{snap['method']}")

    if st.button("Export", type="primary", disabled=not chosen or not stem.strip()):
        folder = Path(st.session_state.export_dir).expanduser()
        try:
            with st.spinner("Writing files…"):
                paths = save_all(view.result, folder, stem.strip(), scale=snap["scale"], artifacts=chosen, recipes=recipes)
        except OSError as e:
            st.error(f"Could not write to {folder}: {e}")
        else:
            st.success(f"Saved {len(paths)} file(s) to {folder}")
            st.code("\n".join(str(p) for p in paths.values()), language=None)


# ------------------------------------------------------------------ main
st.markdown(
    hero_html("Paint by Numbers", "Turn a photograph into a numbered painting template, with acrylic mixing recipes.",
              extra_css=GLOBAL_CSS),
    unsafe_allow_html=True,
)
data, name = choose_image()
if data is None:
    st.stop()
tab_cmp, tab_gen = st.tabs(["Compare methods", "Generate & export"])
with tab_cmp:
    compare_tab(data, name)
with tab_gen:
    generate_tab(data, name)
