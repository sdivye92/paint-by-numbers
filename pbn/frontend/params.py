"""Parameter widgets shared by both tabs."""
from __future__ import annotations

import streamlit as st

from pbn.backend.presets import DEFAULT_COMPACTNESS, PRESETS

COMPACTNESS_OPTIONS = [0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3]


def param_form(prefix: str, method: str | None = None) -> dict:
    """Render every tunable parameter and return them as a flat dict.

    `method` limits the method-specific widgets (None shows both groups). Widget keys include
    the chosen preset, so switching preset resets the sliders to that preset's values.
    """
    detail = st.selectbox(
        "Detail preset", list(PRESETS), key=f"{prefix}_detail",
        help="Starting values for everything below. Low = chunky and easy to paint; high = fine detail, many small regions.",
    )
    p = PRESETS[detail]

    def key(name):
        return f"{prefix}_{detail}_{name}"

    params = {"detail": detail}
    params["size"] = st.slider(
        "Working resolution (px)", 400, 2400, p["size"], 100, key=key("size"),
        help="Long side of the image used for processing. All pixel limits below are in these pixels. "
             "Higher = more detail, slower.")
    params["colors"] = st.slider("Colours", 2, 48, p["colors"], key=key("colors"), help="Number of paints in the palette.")
    params["smooth_iters"] = st.slider(
        "Smoothing passes", 0, 6, p["smooth_iters"], key=key("smooth"),
        help="Edge-preserving smoothing before colour grouping. 0 can look blocky (JPEG artefacts, noise); "
             "too many blurs fine detail. 1-2 is usually best for detailed results.")
    params["min_area"] = st.slider(
        "Min region area (px)", 5, 500, p["min_area"], key=key("area"),
        help="Regions smaller than this are repainted with their closest neighbour's colour.")
    params["min_radius"] = st.slider(
        "Min region radius (px)", 1.0, 10.0, float(p["min_radius"]), 0.5, key=key("radius"),
        help="Regions too thin for a circle of this radius to fit are merged away (can't be painted).")

    if method in (None, "kmeans-potts"):
        if method is None:
            st.markdown("**k-means + Potts**")
        params["lam"] = st.slider(
            "Smoothness (λ)", 0.0, 6.0, float(p["lam"]), 0.1, key=key("lam"),
            help="Penalty for neighbouring pixels having different colours. 0 = plain k-means; higher = smoother, blobbier regions.")
    else:
        params["lam"] = p["lam"]

    if method in (None, "slic-merge"):
        if method is None:
            st.markdown("**SLIC + region merge**")
        params["regions"] = st.slider(
            "Target regions", 50, 4000, p["regions"], 50, key=key("regions"),
            help="Superpixels are merged down to this many regions before colours are assigned.")
        params["superpixels"] = st.slider(
            "Initial superpixels", 500, 30000, p["superpixels"], 500, key=key("superpixels"),
            help="Starting number of superpixels; should be well above the target regions.")
        params["compactness"] = st.select_slider(
            "SLIC compactness", COMPACTNESS_OPTIONS, value=DEFAULT_COMPACTNESS, key=key("compactness"),
            help="CIELAB scale. Low follows colour edges; values of ~1 or more collapse into a square grid.")
    else:
        params["regions"] = p["regions"]
        params["superpixels"] = p["superpixels"]
        params["compactness"] = DEFAULT_COMPACTNESS
    return params
