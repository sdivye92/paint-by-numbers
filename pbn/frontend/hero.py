"""Header artwork.

A stylised "paint-by-numbers" landscape, generated with the app's own region and outline code: smooth
horizontal bands and a few pockets, traced as shared outlines with a tiny number in each region, and a handful of
regions already "painted" in muted tube colours. It fades in from the right so the title stays clean.

Colours are mid-tones with low opacity, so the same artwork reads on both the light and the dark theme.
"""
from __future__ import annotations

import base64
from functools import lru_cache

import cv2
import numpy as np
from scipy import ndimage
from scipy.ndimage import gaussian_filter1d

from pbn.backend.regions import clean_regions, connected_components
from pbn.backend.render import fit_text, region_table, trace_chains

W, H = 1200, 200  # SVG units
GW, GH = 360, 60  # label grid; one cell = W / GW units
K = W / GW
BANDS = 11
UP = 4  # supersampling for the painted-region outlines
INK = "#8c7a66"  # mid-tone ink that reads on light and dark backgrounds
# muted tube colours, sky (top) to horizon and water (bottom)
BAND_COLOURS = ["#34406e", "#3f4a7a", "#4f5b8c", "#6d6590", "#85536f", "#8e4a62", "#a85a40", "#c27a45", "#c9a04a",
                "#7b6a52", "#4a5a4c"]


def _field(seed: int) -> np.ndarray:
    """Smooth scalar field: roughly 'depth down the page' plus gentle waves and a couple of pockets."""
    rng = np.random.default_rng(seed)
    yy, xx = np.meshgrid(np.linspace(0, 1, GH), np.linspace(0, 1, GW), indexing="ij")
    f = 0.85 * yy
    for amp, freq in ((0.10, 1.1), (0.06, 2.6), (0.035, 5.0), (0.02, 9.0)):
        f += amp * np.sin(2 * np.pi * (freq * xx + rng.uniform() + yy * rng.uniform(-0.8, 0.8)))
    for cx, cy, sx, sy, a in ((0.80, 0.42, 0.06, 0.15, -0.30), (0.58, 0.62, 0.05, 0.10, 0.18), (0.93, 0.70, 0.05, 0.12, -0.20),
                              (0.66, 0.28, 0.04, 0.09, -0.16), (0.88, 0.25, 0.05, 0.10, 0.14), (0.46, 0.50, 0.04, 0.08, -0.15),
                              (0.72, 0.80, 0.06, 0.08, 0.16)):
        f += a * np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
    return f


def _labels(seed: int) -> np.ndarray:
    f = _field(seed)
    edges = np.quantile(f, np.linspace(0, 1, BANDS + 1)[1:-1])
    labels = np.digitize(f, edges).astype(np.int32)
    proxy = np.c_[np.arange(BANDS) * 12.0, np.zeros(BANDS), np.zeros(BANDS)]  # only needs an ordering of bands
    return clean_regions(labels, proxy, min_area=14, min_radius=2.0)


def _painted_paths(cc: np.ndarray, ids: list[int]) -> dict[int, str]:
    """Smoothed outline path (with holes) for each region id, from a supersampled mask."""
    big = np.repeat(np.repeat(cc, UP, 0), UP, 1)
    boxes = ndimage.find_objects(cc)
    out = {}
    for rid in ids:
        sl = boxes[rid - 1]
        y0, x0 = sl[0].start * UP, sl[1].start * UP
        mask = np.pad((big[sl[0].start * UP:sl[0].stop * UP, sl[1].start * UP:sl[1].stop * UP] == rid).astype(np.uint8), 1)
        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        parts = []
        for c in contours:
            pts = c.reshape(-1, 2).astype(np.float64)
            if len(pts) < 8:
                continue
            pts = gaussian_filter1d(pts, 7, axis=0, mode="wrap")
            pts = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), 0.7, True).reshape(-1, 2)
            pts = ((pts - 1 + [x0, y0] + 0.5) / UP) * K
            parts.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z")
        if parts:
            out[rid] = " ".join(parts)
    return out


@lru_cache(maxsize=1)
def hero_svg(seed: int = 11) -> str:
    labels = _labels(seed)
    cc, n = connected_components(labels)
    table = region_table(labels)
    rng = np.random.default_rng(seed + 1)
    painted = [i + 1 for i in range(n) if table["area"][i] >= 40 and rng.random() < 0.3]
    fills = _painted_paths(cc, painted)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMaxYMid slice">',
        '<defs><linearGradient id="f" x1="0" x2="1" y1="0" y2="0">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".22" stop-color="#fff" stop-opacity=".06"/>'
        '<stop offset=".45" stop-color="#fff" stop-opacity=".4"/><stop offset=".72" stop-color="#fff" stop-opacity=".9"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>'
        f'<mask id="m"><rect width="{W}" height="{H}" fill="url(#f)"/></mask></defs>',
        '<g mask="url(#m)">',
    ]
    for rid, d in fills.items():
        colour = BAND_COLOURS[int(table["label"][rid - 1])]
        svg.append(f'<path d="{d}" fill="{colour}" fill-opacity=".45" fill-rule="evenodd"/>')
    svg.append(f'<g fill="none" stroke="{INK}" stroke-opacity=".85" stroke-width="1.1" stroke-linejoin="round" stroke-linecap="round">')
    for pts, closed in trace_chains(labels, sigma=2.0, eps=0.5):
        d = "M" + " L".join(f"{x * K:.1f} {y * K:.1f}" for x, y in pts)
        svg.append(f'<path d="{d}{" Z" if closed else ""}"/>')
    svg.append("</g>")
    svg.append(f'<g font-family="Helvetica,Arial,sans-serif" text-anchor="middle" dominant-baseline="central" '
               f'fill="{INK}" fill-opacity="1">')
    for lab, x, y, r in zip(table["label"], table["x"], table["y"], table["radius"]):
        text = str(int(lab) + 1)
        h = fit_text(text, r * K, 10.5)
        if h >= 3.2:
            svg.append(f'<text x="{x * K:.1f}" y="{y * K:.1f}" font-size="{h / 0.72:.1f}">{text}</text>')
    svg.append("</g></g></svg>")
    return "".join(svg)


def hero_html(title: str, subtitle: str, extra_css: str = "") -> str:
    """Title and description over the artwork. No blank lines, so Streamlit's markdown keeps it one HTML block."""
    uri = base64.b64encode(hero_svg().encode()).decode()
    css = (
        ".pbn-hero{position:relative;margin:-.5rem 0 1.75rem;padding:.4rem 0 1.1rem;min-height:11rem;"
        f"background:url('data:image/svg+xml;base64,{uri}') right center/cover no-repeat;"
        "border-bottom:1px solid rgba(140,122,102,.35)}"
        ".pbn-hero h1{padding-top:1.4rem}"
        ".pbn-hero p{font-size:1.2rem;line-height:1.55;max-width:32rem;opacity:.82;margin:0}"
        + extra_css
    )
    return f"<style>{css}</style><div class='pbn-hero'><h1>{title}</h1><p>{subtitle}</p></div>"
