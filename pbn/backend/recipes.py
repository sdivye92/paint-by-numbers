"""Turn a Result's palette into paint recipes, quantities and printable sheets."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .imageops import rgb2lab
from .paints import STANDARD_SET, Paint, build_library, match, refine, rgb_to_hex
from .result import Result

MAX_ENUMERATED = 4  # up to this many tubes per mix is searched exhaustively; more is refined by local search
MAX_TUBES = 6


@dataclass
class Recipe:
    number: int  # paint-by-number number (1-based)
    target_rgb: tuple[int, int, int]
    mix_rgb: tuple[int, int, int]  # predicted colour of the mix
    delta_e: float  # CIEDE2000 between target and predicted mix
    parts: list[tuple[str, int]]  # (paint name, parts), most first
    coverage: float  # share of the canvas
    total_ml: float = 0.0
    ml: list[tuple[str, float]] = field(default_factory=list)

    @property
    def text(self) -> str:
        total = sum(p for _, p in self.parts)

        def one(name, p):
            touch = " (a touch)" if len(self.parts) > 1 and p / total < 0.04 else ""
            return f"{p} part{'s' if p != 1 else ''} {name}{touch}"

        return " + ".join(one(name, p) for name, p in self.parts)

    @property
    def quality(self) -> str:
        return "excellent" if self.delta_e < 2 else "good" if self.delta_e < 5 else "approximate"


def build_recipes(
    result: Result,
    paints=STANDARD_SET,
    max_paints: int = 3,
    canvas_cm: tuple[float, float] = (40.0, 50.0),
    ml_per_100cm2: float = 1.5,
    coats: int = 2,
    margin: float = 0.25,
    tube_penalty: float = 1.0,
) -> list[Recipe]:
    """Best mix of `paints` for every palette colour, with a volume estimate per paint.

    Volume = canvas area x share of canvas x ml per 100 cm2 per coat x coats x (1 + margin).
    The coverage rate is a rough default for medium-body acrylics; adjust it to your painting style.

    `max_paints` (2-6) caps the tubes per mix and `tube_penalty` is the cost, in dE2000 units, of each
    tube beyond the first: 1.0 favours simple recipes, ~0.25 buys accuracy with more tubes.
    See paints.py (match / refine) for the optimisation.
    """
    paints = tuple(paints)
    lib = build_library(paints, min(max_paints, MAX_ENUMERATED))
    cov = np.bincount(result.labels.ravel(), minlength=result.k) / result.labels.size
    area_cm2 = canvas_cm[0] * canvas_cm[1]
    recipes = []
    for i, (lab, rgb) in enumerate(zip(result.palette_lab, result.palette_rgb)):
        if max_paints > MAX_ENUMERATED:  # 5-6 tubes: refine the best library recipes by local search
            row, de, mix_colour = refine(lib, lab, max_paints, w_paints=tube_penalty)
        else:
            idx, de = match(lib, lab, w_paints=tube_penalty)
            row, mix_colour = lib.parts[idx], lib.rgb[idx]
        parts = sorted(((paints[j].name, int(row[j])) for j in np.flatnonzero(row)), key=lambda t: -t[1])
        total_ml = float(cov[i] * area_cm2 / 100.0 * ml_per_100cm2 * coats * (1.0 + margin))
        denom = sum(p for _, p in parts)
        recipes.append(Recipe(
            number=i + 1,
            target_rgb=tuple(int(v) for v in rgb),
            mix_rgb=tuple(int(round(v)) for v in mix_colour),
            delta_e=de,
            parts=parts,
            coverage=float(cov[i]),
            total_ml=total_ml,
            ml=[(name, total_ml * p / denom) for name, p in parts],
        ))
    return recipes


def mix_preview_image(result: Result, recipes: list[Recipe]) -> np.ndarray:
    """The template repainted with each recipe's *predicted mixed colour* instead of the palette colour."""
    palette = np.array([r.mix_rgb for r in recipes], np.uint8)  # recipes are in palette order
    return palette[result.labels]


def preview_error(original_rgb: np.ndarray, preview_rgb: np.ndarray) -> float:
    """Mean CIELAB distance (dE76) per pixel between the photo and a preview of it."""
    diff = rgb2lab(original_rgb) - rgb2lab(preview_rgb)
    return float(np.linalg.norm(diff, axis=2).mean())


def usage_summary(recipes: list[Recipe]) -> dict[str, float]:
    """Total ml needed of each tube across all recipes, largest first."""
    use: dict[str, float] = {}
    for r in recipes:
        for name, ml in r.ml:
            use[name] = use.get(name, 0.0) + ml
    return dict(sorted(use.items(), key=lambda kv: -kv[1]))


def recipes_csv(recipes: list[Recipe]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["number", "target_hex", "predicted_hex", "delta_e2000", "match", "recipe", "coverage_pct", "total_ml", "ml_by_paint"])
    for r in recipes:
        w.writerow([
            r.number, rgb_to_hex(r.target_rgb), rgb_to_hex(r.mix_rgb), round(r.delta_e, 2), r.quality, r.text,
            round(100 * r.coverage, 1), round(r.total_ml, 1),
            "; ".join(f"{name}: {ml:.1f} ml" for name, ml in r.ml),
        ])
    return buf.getvalue()


def recipe_sheet_image(recipes: list[Recipe], usage: dict[str, float] | None = None) -> np.ndarray:
    """A printable PNG: for each number, target swatch, predicted-mix swatch, recipe and amounts."""
    usage = usage if usage is not None else usage_summary(recipes)
    W, row_h, top = 1500, 60, 70
    foot = 50 + 28 * (len(usage) + 1)
    img = Image.new("RGB", (W, top + row_h * len(recipes) + foot), "white")
    d = ImageDraw.Draw(img)
    big, font, small = (ImageFont.load_default(size=s) for s in (22, 17, 14))
    d.text((16, 14), "Paint recipes", fill=(0, 0, 0), font=big)
    d.text((16, 44), "parts are by volume (e.g. a palette-knife scoop or a spoon); swatches: target | predicted mix",
           fill=(110, 110, 110), font=small)
    for n, r in enumerate(recipes):
        y = top + n * row_h
        d.text((16, y + 14), str(r.number), fill=(0, 0, 0), font=big)
        d.rectangle([70, y + 6, 120, y + row_h - 8], fill=r.target_rgb, outline=(90, 90, 90))
        d.rectangle([126, y + 6, 176, y + row_h - 8], fill=r.mix_rgb, outline=(90, 90, 90))
        d.text((196, y + 6), r.text, fill=(20, 20, 20), font=font)
        amounts = ", ".join(f"{ml:.1f} ml {name}" for name, ml in r.ml)
        d.text((196, y + 31), f"~{r.total_ml:.1f} ml total: {amounts}", fill=(110, 110, 110), font=small)
        d.text((W - 190, y + 14), f"dE {r.delta_e:.1f} ({r.quality})", fill=(20, 20, 20), font=font)
        d.line([(16, y + row_h - 1), (W - 16, y + row_h - 1)], fill=(230, 230, 230))
    y = top + row_h * len(recipes) + 20
    d.text((16, y), "Total paint needed (ml)", fill=(0, 0, 0), font=big)
    for n, (name, ml) in enumerate(usage.items()):
        d.text((30, y + 32 + n * 28), f"{name}: {ml:.0f} ml", fill=(30, 30, 30), font=font)
    return np.asarray(img)
