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
from pbn.backend.package import build_package, package_filenames, safe_name
from pbn.backend.render import ARTIFACTS, RECIPE_ARTIFACTS
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


def _package_info(snap: dict, recipes) -> dict:
    """What went into the package, so a ZIP can be reproduced or understood months later."""
    info = {"image": snap["name"], "method": snap["method"], "settings": snap["params"], "output_scale": snap["scale"]}
    if recipes:
        ss = st.session_state
        info["paint_recipes"] = {
            "canvas_cm": [ss.get("canvas_w"), ss.get("canvas_h")], "ml_per_100cm2": ss.get("ml_rate"),
            "coats": ss.get("coats"), "max_tubes": ss.get("max_paints"), "recipe_style": ss.get("recipe_style"),
            "tubes_used": sorted({name for r in recipes for name, _ in r.parts}),
        }
    return info


def export_section(snap: dict, view, recipes=None):
    st.subheader("Download")
    options = list(ARTIFACTS) + (list(RECIPE_ARTIFACTS) if recipes else [])
    chosen = st.multiselect("Artifacts", options, default=options, format_func=ARTIFACT_LABELS.get)
    stem = st.text_input("Package name", value=f"{snap['name']}_{snap['method']}", key=f"stem_{snap['name']}_{snap['method']}",
                         help="Used as the ZIP's file name and as the folder inside it.")
    clean = safe_name(stem)
    result, scale, info = view.result, snap["scale"], _package_info(snap, recipes)

    def build() -> bytes:
        """Runs when the button is clicked (on a worker thread): renders the files and returns the ZIP."""
        return build_package(result, clean, list(chosen), scale, recipes, info)[0]

    st.download_button("Download ZIP", build, file_name=f"{clean}.zip", mime="application/zip", type="primary",
                       key="dl_zip", on_click="ignore", disabled=not chosen or not stem.strip())
    st.caption("The ZIP is built when you click and goes to your browser as a normal download, so it is saved on your "
               "computer, never on the server. Your browser decides the folder (most can be set to ask).")
    with st.expander("Files in the package"):
        st.code("\n".join(package_filenames(clean, chosen)), language=None)


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
