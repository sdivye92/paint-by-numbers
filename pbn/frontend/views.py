"""Cached pipeline runs for the app."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import streamlit as st

from pbn.backend.compare import metrics
from pbn.backend.imageops import load_image_bytes
from pbn.backend.methods import run_method
from pbn.backend.presets import method_opts
from pbn.backend.render import legend_image, outline_image, preview_image, region_table, trace_chains
from pbn.backend.result import Result

METHOD_LABELS = {
    "kmeans-potts": "k-means + Potts graph cut",
    "slic-merge": "SLIC + region merge",
}
DISPLAY_SCALE = 2  # outline raster scale used for on-screen display (exports use their own scale)


@dataclass
class View:
    result: Result
    preview: np.ndarray
    outline: np.ndarray
    legend: np.ndarray
    metrics: dict


@st.cache_resource(show_spinner=False, max_entries=8)
def run_view(data: bytes, method: str, params: tuple) -> View:
    """Run one method on an encoded image. Cached on (image bytes, method, params)."""
    p = dict(params)
    rgb = load_image_bytes(data, p["size"])
    result = run_method(method, rgb, **method_opts(p))
    chains = trace_chains(result.labels)
    table = region_table(result.labels)
    return View(
        result=result,
        preview=preview_image(result),
        outline=outline_image(result, chains, table, DISPLAY_SCALE),
        legend=legend_image(result),
        metrics=metrics(result),
    )


def freeze(params: dict) -> tuple:
    return tuple(sorted(params.items()))
