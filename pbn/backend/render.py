"""Turn a label map into printable output: shared-boundary vector outlines, numbers, legend."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter1d

from .recipes import mix_preview_image, recipe_sheet_image, recipes_csv
from .regions import connected_components, region_geometry
from .result import Result

FONT = cv2.FONT_HERSHEY_SIMPLEX


# --------------------------------------------------------------------------- boundaries
def trace_chains(labels: np.ndarray, sigma: float = 2.0, eps: float = 0.6):
    """Trace region boundaries along pixel edges, as polylines shared by both neighbours.

    Every boundary edge between two differently-labelled pixels (and the image border) is
    a segment between pixel corners. Chains run between junction corners (degree != 2), so
    each boundary is stored exactly once: no gaps or double lines. Chains are then smoothed
    (Gaussian along the chain, junctions pinned) and simplified (Douglas-Peucker).
    Returns a list of (points (m,2) float32 in pixel-corner coords, closed: bool).
    """
    H, W = labels.shape
    P = np.pad(labels, 1, constant_values=-1)
    hm = P[:-1, 1:-1] != P[1:, 1:-1]  # (H+1, W): edge (y,x)-(y,x+1)
    vm = P[1:-1, :-1] != P[1:-1, 1:]  # (H, W+1): edge (y,x)-(y+1,x)
    W1 = W + 1
    N = (H + 1) * W1
    nbr = np.full((N, 4), -1, np.int64)  # slots: 0 right, 1 down, 2 left, 3 up
    ys, xs = np.nonzero(hm)
    a = ys * W1 + xs
    nbr[a, 0] = a + 1
    nbr[a + 1, 2] = a
    ys, xs = np.nonzero(vm)
    a = ys * W1 + xs
    nbr[a, 1] = a + W1
    nbr[a + W1, 3] = a

    deg = (nbr >= 0).sum(1)
    stop = deg != 2
    stop[[0, W, H * W1, H * W1 + W]] = True  # keep the page corners sharp
    stop_l = stop.tolist()
    nbr_l = nbr.tolist()
    used = bytearray(N * 4)

    def walk(start, s):
        path = [start]
        cur = start
        while True:
            nxt = nbr_l[cur][s]
            used[cur * 4 + s] = 1
            used[nxt * 4 + ((s + 2) & 3)] = 1
            path.append(nxt)
            if stop_l[nxt] or nxt == start:
                return path
            back = (s + 2) & 3
            for s2 in range(4):
                if s2 != back and nbr_l[nxt][s2] >= 0:
                    s = s2
                    break
            cur = nxt

    paths = []
    for node in np.flatnonzero(stop & (deg > 0)).tolist():
        for s in range(4):
            if nbr_l[node][s] >= 0 and not used[node * 4 + s]:
                paths.append(walk(node, s))
    for node in np.flatnonzero(deg > 0).tolist():  # remaining pure loops (islands)
        for s in range(4):
            if nbr_l[node][s] >= 0 and not used[node * 4 + s]:
                paths.append(walk(node, s))

    chains = []
    for path in paths:
        ids = np.asarray(path)
        pts = np.stack([ids % W1, ids // W1], 1).astype(np.float64)
        closed = path[0] == path[-1] and not stop_l[path[0]]
        if closed:
            body = pts[:-1]
            if len(body) >= 4:
                body = gaussian_filter1d(body, sigma, axis=0, mode="wrap")
            pts = np.vstack([body, body[:1]])
        elif len(pts) >= 4:
            first, last = pts[0].copy(), pts[-1].copy()
            pts = gaussian_filter1d(pts, sigma, axis=0, mode="nearest")
            pts[0], pts[-1] = first, last
        approx = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), eps, False).reshape(-1, 2)
        chains.append((approx, closed))
    return chains


# --------------------------------------------------------------------------- numbers
def region_table(labels: np.ndarray) -> dict[str, np.ndarray]:
    """One row per connected region: palette label, centre (x, y), inscribed radius, area."""
    cc, n = connected_components(labels)
    area, radius, pos = region_geometry(cc, n)
    label_of = np.zeros(n + 1, np.int64)
    label_of[cc.ravel()] = labels.ravel()
    return {
        "label": label_of[1:],
        "x": pos[:, 1] + 0.5,
        "y": pos[:, 0] + 0.5,
        "radius": radius,
        "area": area,
    }


def fit_text(text: str, radius: float, max_h: float) -> float:
    """Digit height (same units as `radius`) so the text box fits inside a circle of `radius`."""
    (w1, h1), _ = cv2.getTextSize(text, FONT, 1.0, 1)
    h = 0.9 * radius * h1 / (0.5 * np.hypot(w1, h1))
    return min(h, max_h)


# --------------------------------------------------------------------------- outputs
def preview_image(result: Result) -> np.ndarray:
    return result.palette_rgb[result.labels]


def outline_image(result: Result, chains, table, scale: int = 3, max_digit_h: float = 8.0) -> np.ndarray:
    H, W = result.labels.shape
    img = np.full((H * scale, W * scale, 3), 255, np.uint8)
    shift = 4
    for pts, closed in chains:
        q = np.round(pts * scale * (1 << shift)).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [q], False, (35, 35, 35), 1, cv2.LINE_AA, shift)
    for lab, x, y, r in zip(table["label"], table["x"], table["y"], table["radius"]):
        text = str(int(lab) + 1)
        h = fit_text(text, r * scale, max_digit_h * scale)
        if h < 4:
            continue
        (w1, h1), _ = cv2.getTextSize(text, FONT, 1.0, 1)
        fs = h / h1
        (tw, th), _ = cv2.getTextSize(text, FONT, fs, 1)
        org = (int(round(x * scale - tw / 2)), int(round(y * scale + th / 2)))
        cv2.putText(img, text, org, FONT, fs, (70, 70, 70), 1, cv2.LINE_AA)
    return img


def svg_document(result: Result, chains, table, scale: int = 3, max_digit_h: float = 8.0) -> str:
    H, W = result.labels.shape
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W * scale}" height="{H * scale}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g fill="none" stroke="#232323" stroke-width="0.35" stroke-linejoin="round" stroke-linecap="round">',
    ]
    for pts, closed in chains:
        d = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts)
        out.append(f'<path d="{d}{" Z" if closed else ""}"/>')
    out.append("</g>")
    out.append('<g font-family="Helvetica, Arial, sans-serif" text-anchor="middle" '
               'dominant-baseline="central" fill="#464646">')
    for lab, x, y, r in zip(table["label"], table["x"], table["y"], table["radius"]):
        text = str(int(lab) + 1)
        h = fit_text(text, r, max_digit_h)
        if h < 1.3:
            continue
        out.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{h / 0.72:.2f}">{text}</text>')
    out.append("</g></svg>")
    return "\n".join(out)


def coverage(result: Result) -> np.ndarray:
    return np.bincount(result.labels.ravel(), minlength=result.k) / result.labels.size


def hex_colour(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*map(int, rgb))


def legend_image(result: Result) -> np.ndarray:
    cov = coverage(result)
    row = 38
    img = Image.new("RGB", (300, row * result.k + 10), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=17)
    for i, (rgb, c) in enumerate(zip(result.palette_rgb, cov)):
        y = 6 + i * row
        d.rectangle([10, y, 70, y + row - 8], fill=tuple(int(v) for v in rgb), outline=(90, 90, 90))
        d.text((84, y + 5), f"{i + 1}", fill=(0, 0, 0), font=font)
        d.text((130, y + 5), f"{hex_colour(rgb)}   {100 * c:4.1f}%", fill=(60, 60, 60), font=font)
    return np.asarray(img)


ARTIFACTS = ("preview", "outline", "svg", "legend", "json")
RECIPE_ARTIFACTS = ("recipes_png", "recipes_csv", "mix_preview")  # need `recipes` passed to save_all


def save_all(result: Result, out_dir: str | Path, stem: str, scale: int = 3, artifacts=ARTIFACTS,
             recipes=None) -> dict:
    """Write the chosen artifacts: preview/outline/legend PNGs, outline SVG, palette JSON and,
    when `recipes` (from build_recipes) is given, the paint-recipe sheet (PNG) and table (CSV).

    `artifacts` is any subset of ARTIFACTS + RECIPE_ARTIFACTS; returns {artifact: path} for what was written.
    """
    wanted = set(artifacts)
    unknown = wanted - set(ARTIFACTS) - set(RECIPE_ARTIFACTS)
    if unknown:
        raise ValueError(f"Unknown artifacts: {sorted(unknown)}")
    if wanted & set(RECIPE_ARTIFACTS) and recipes is None:
        raise ValueError("Recipe artifacts requested but no recipes were given")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    needs_geometry = wanted & {"outline", "svg", "json"}
    chains = trace_chains(result.labels) if wanted & {"outline", "svg"} else None
    table = region_table(result.labels) if needs_geometry else None

    def write_png(name, rgb):
        path = out_dir / f"{stem}_{name}.png"
        cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return path

    paths = {}
    if "preview" in wanted:
        paths["preview"] = write_png("preview", preview_image(result))
    if "outline" in wanted:
        paths["outline"] = write_png("outline", outline_image(result, chains, table, scale))
    if "legend" in wanted:
        paths["legend"] = write_png("legend", legend_image(result))
    if "svg" in wanted:
        svg_path = out_dir / f"{stem}_outline.svg"
        svg_path.write_text(svg_document(result, chains, table, scale), encoding="utf-8")
        paths["svg"] = svg_path
    if "json" in wanted:
        cov = coverage(result)
        meta = {
            "method": result.name,
            "regions": int(len(table["label"])),
            "palette": [
                {"number": i + 1, "hex": hex_colour(c), "coverage": round(float(p), 4)}
                for i, (c, p) in enumerate(zip(result.palette_rgb, cov))
            ],
        }
        if recipes is not None:
            for entry, r in zip(meta["palette"], recipes):
                entry["recipe"] = [{"paint": name, "parts": p} for name, p in r.parts]
                entry["recipe_delta_e"] = round(r.delta_e, 2)
                entry["ml"] = {name: round(ml, 2) for name, ml in r.ml}
        json_path = out_dir / f"{stem}_palette.json"
        json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        paths["json"] = json_path
    if "recipes_png" in wanted:
        paths["recipes_png"] = write_png("recipes", recipe_sheet_image(recipes))
    if "mix_preview" in wanted:
        paths["mix_preview"] = write_png("mix_preview", mix_preview_image(result, recipes))
    if "recipes_csv" in wanted:
        csv_path = out_dir / f"{stem}_recipes.csv"
        csv_path.write_text(recipes_csv(recipes), encoding="utf-8")
        paths["recipes_csv"] = csv_path
    return paths
