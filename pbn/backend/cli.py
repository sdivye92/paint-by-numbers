from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cv2

from .compare import contact_sheet, metrics
from .imageops import load_image
from .methods import METHODS, run_method
from .package import make_zip
from .paints import STANDARD_SET
from .presets import DEFAULT_COMPACTNESS, PRESETS, method_opts
from .recipes import build_recipes
from .render import ARTIFACTS, RECIPE_ARTIFACTS, save_all


def _add_common(p: argparse.ArgumentParser):
    p.add_argument("-o", "--out", default="out", help="output directory")
    p.add_argument("--detail", choices=list(PRESETS), default="low",
                   help="preset for all the knobs below (default: low); explicit flags override it")
    p.add_argument("-k", "--colors", type=int, help="palette size")
    p.add_argument("--size", type=int, help="working resolution (long side, px)")
    p.add_argument("--min-area", type=int, help="smallest allowed region, px")
    p.add_argument("--min-radius", type=float, help="smallest allowed inscribed radius, px")
    p.add_argument("--smooth-iters", type=int, help="bilateral smoothing passes (0 = none)")
    p.add_argument("--lam", type=float, help="[kmeans-potts] smoothness weight (0 = plain k-means)")
    p.add_argument("--regions", type=int, help="[slic-merge] target region count before palette merge")
    p.add_argument("--superpixels", type=int, help="[slic-merge] initial superpixel count")
    p.add_argument("--compactness", type=float, default=DEFAULT_COMPACTNESS,
                   help="[slic-merge] SLIC compactness (Lab scale: ~0.01-0.3; >=1 gives a square grid)")
    p.add_argument("--scale", type=int, default=3, help="output scale for outline.png / svg size")


def _resolve(a):
    """Fill every option the user did not pass from the chosen --detail preset."""
    for key, value in PRESETS[a.detail].items():
        if getattr(a, key) is None:
            setattr(a, key, value)
    return a


def _opts(a) -> dict:
    return method_opts(vars(a))


def launch_app(port: int = 8501):
    app_path = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)], check=True)
    except subprocess.CalledProcessError:
        sys.exit("Could not start Streamlit. Is it installed?  pip install streamlit")
    except KeyboardInterrupt:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pbn", description="Photo -> paint-by-numbers template")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="convert one image with one method")
    run.add_argument("image")
    run.add_argument("-m", "--method", choices=list(METHODS), default="kmeans-potts")
    _add_common(run)
    run.add_argument("--recipes", action="store_true",
                     help="also write acrylic mixing recipes (standard 12-tube set) as a PNG sheet and CSV")
    run.add_argument("--tube-penalty", type=float, default=1.0,
                     help="cost per extra tube in dE units: 1.0 simple recipes (default), ~0.25 more accurate with more tubes")
    run.add_argument("--zip", action="store_true", help="also bundle everything into <name>.zip")
    run.add_argument("--canvas", default="40x50", help="canvas size WxH in cm, for paint quantities (default 40x50)")
    run.add_argument("--max-paints", type=int, default=3, choices=[2, 3, 4, 5, 6],
                     help="max tubes per mix (default 3; 5-6 refine hard colours by local search)")
    run.add_argument("--ml-per-100cm2", type=float, default=1.5, help="paint per 100 cm2 per coat, ml (default 1.5)")
    run.add_argument("--coats", type=int, default=2, help="number of coats (default 2)")

    cmp_ = sub.add_parser("compare", help="run both methods on one or more images and build a side-by-side sheet")
    cmp_.add_argument("images", nargs="+")
    _add_common(cmp_)

    app = sub.add_parser("app", help="launch the Streamlit app")
    app.add_argument("--port", type=int, default=8501)

    a = ap.parse_args(argv)
    if a.cmd == "app":
        return launch_app(a.port)
    a = _resolve(a)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    if a.cmd == "run":
        rgb = load_image(a.image, a.size)
        res = run_method(a.method, rgb, **_opts(a))
        recipes, artifacts = None, ARTIFACTS
        if a.recipes:
            w, h = (float(v) for v in a.canvas.lower().split("x"))
            recipes = build_recipes(res, STANDARD_SET, a.max_paints, (w, h), a.ml_per_100cm2, a.coats,
                                    tube_penalty=a.tube_penalty)
            artifacts = ARTIFACTS + RECIPE_ARTIFACTS
        stem = f"{Path(a.image).stem}_{res.name}"
        paths = save_all(res, out, stem, a.scale, artifacts, recipes)
        print(metrics(res))
        if recipes:
            for r in recipes:
                print(f"  {r.number:>2}: {r.text}  (dE {r.delta_e:.1f}, ~{r.total_ml:.1f} ml)")
        for k, v in paths.items():
            print(f"  {k:8s} {v}")
        if a.zip:
            info = {"image": Path(a.image).name, "method": a.method, "detail": a.detail, "size": a.size,
                    "parameters": _opts(a), "output_scale": a.scale}
            if recipes:
                info["paint_recipes"] = {"canvas_cm": a.canvas, "max_tubes": a.max_paints, "tube_penalty": a.tube_penalty,
                                         "ml_per_100cm2": a.ml_per_100cm2, "coats": a.coats}
            zip_path = out / f"{stem}.zip"
            zip_path.write_bytes(make_zip(paths, stem, info))
            print(f"  {'zip':8s} {zip_path}")
    else:
        for image in a.images:
            stem = Path(image).stem
            rgb = load_image(image, a.size)
            results = []
            for name in METHODS:
                res = run_method(name, rgb, **_opts(a))
                save_all(res, out / stem, res.name, a.scale)
                print(metrics(res))
                results.append(res)
            sheet = contact_sheet(rgb, results, scale=2)
            sheet_path = out / f"compare_{stem}.png"
            cv2.imwrite(str(sheet_path), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
            print(f"  sheet    {sheet_path}")


if __name__ == "__main__":
    main()
