"""Metrics and side-by-side contact sheets for comparing the two methods."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .imageops import rgb2lab
from .regions import connected_components, region_geometry
from .render import outline_image, preview_image, region_table, trace_chains
from .result import Result


def metrics(result: Result) -> dict:
    cc, n = connected_components(result.labels)
    area, radius, _ = region_geometry(cc, n)
    err = np.linalg.norm(rgb2lab(result.original_rgb) - result.palette_lab[result.labels], axis=2)
    return {
        "method": result.name,
        "colors": result.k,
        "regions": n,
        "median_area": int(np.median(area)),
        "min_area": int(area.min()),
        "min_radius": round(float(radius.min()), 1),
        "mean_dE": round(float(err.mean()), 2),
        "seconds": round(sum(result.timings.values()), 1),
    }


def _label(img: np.ndarray, text: str) -> np.ndarray:
    bar = Image.new("RGB", (img.shape[1], 34), (245, 245, 245))
    ImageDraw.Draw(bar).text((8, 7), text, fill=(0, 0, 0), font=ImageFont.load_default(size=17))
    return np.vstack([np.asarray(bar), img])


def contact_sheet(original: np.ndarray, results: list[Result], scale: int = 2) -> np.ndarray:
    """Columns: original | each method.  Rows: colour preview, numbered outline."""
    H, W = original.shape[:2]
    size = (W * scale, H * scale)
    blank = np.full((H * scale, W * scale, 3), 255, np.uint8)
    top = [_label(cv2.resize(original, size, interpolation=cv2.INTER_CUBIC), "original")]
    bottom = [_label(blank, "")]
    for r in results:
        m = metrics(r)
        caption = f"{r.name}: {m['colors']} colours, {m['regions']} regions, dE {m['mean_dE']}, {m['seconds']}s"
        top.append(_label(cv2.resize(preview_image(r), size, interpolation=cv2.INTER_NEAREST), caption))
        bottom.append(_label(outline_image(r, trace_chains(r.labels), region_table(r.labels), scale), "outline"))
    return np.vstack([np.hstack(top), np.hstack(bottom)])
