"""Detail presets shared by the CLI and the Streamlit app.

More detail = higher working resolution, smaller allowed regions, less smoothing, more colours.
Sizes are in working-resolution pixels, so what is *paintable* depends on the print size too.
"""
from __future__ import annotations

PRESETS = {
    "low":    dict(size=800,  colors=16, min_area=120, min_radius=4.0, smooth_iters=3, lam=2.0, regions=300,  superpixels=4000),
    "medium": dict(size=1200, colors=20, min_area=70,  min_radius=3.0, smooth_iters=2, lam=1.5, regions=800,  superpixels=9000),
    "high":   dict(size=1600, colors=24, min_area=40,  min_radius=2.5, smooth_iters=1, lam=1.0, regions=1800, superpixels=20000),
}
DEFAULT_COMPACTNESS = 0.05  # CIELAB scale; values >= ~1 collapse SLIC into a square grid


def method_opts(p: dict) -> dict:
    """Map a flat parameter dict (preset keys + compactness) to run_method() keyword arguments."""
    return dict(
        k=p["colors"],
        lam=p["lam"],
        regions=p["regions"],
        superpixels=p["superpixels"],
        compactness=p.get("compactness", DEFAULT_COMPACTNESS),
        smooth_iters=p["smooth_iters"],
        min_area=p["min_area"],
        min_radius=p["min_radius"],
    )
