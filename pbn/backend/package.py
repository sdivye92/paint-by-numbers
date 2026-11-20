"""Bundle exported artifacts into a single ZIP archive (used by the web app's Export and by `run --zip`)."""
from __future__ import annotations

import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

from .render import ARTIFACTS, save_all
from .result import Result


def safe_name(name: str, default: str = "paint_by_numbers") -> str:
    """A file-system-safe name: no path separators or odd characters, never empty."""
    cleaned = re.sub(r"[^\w.\- ]+", "_", name).strip(" ._")
    return cleaned or default


def make_zip(files: dict[str, Path], root: str, info: dict | None = None) -> bytes:
    """ZIP the given files into one folder named `root`, optionally with a `package_info.json`."""
    root = safe_name(root)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in files.values():
            z.write(path, f"{root}/{Path(path).name}")
        if info is not None:
            z.writestr(f"{root}/package_info.json", json.dumps(info, indent=2, default=str))
    return buf.getvalue()


def build_package(
    result: Result,
    stem: str,
    artifacts=ARTIFACTS,
    scale: int = 3,
    recipes=None,
    info: dict | None = None,
) -> tuple[bytes, list[str]]:
    """Render the chosen artifacts and return (zip bytes, names of the files inside the archive).

    Files are written to a temporary folder first (nothing is left on disk), so the same renderers
    serve the CLI, the folder export and the web app.
    """
    stem = safe_name(stem)
    with tempfile.TemporaryDirectory() as tmp:
        paths = save_all(result, tmp, stem, scale=scale, artifacts=artifacts, recipes=recipes)
        data = make_zip(paths, stem, info)
    names = [f"{stem}/{Path(p).name}" for p in paths.values()]
    if info is not None:
        names.append(f"{stem}/package_info.json")
    return data, names


# File-name suffix of every artifact, in the order the package lists them (mirrors render.save_all).
_SUFFIX = {
    "preview": "_preview.png", "outline": "_outline.png", "svg": "_outline.svg", "legend": "_legend.png",
    "json": "_palette.json", "recipes_png": "_recipes.png", "recipes_csv": "_recipes.csv", "mix_preview": "_mix_preview.png",
}


def package_filenames(stem: str, artifacts, with_info: bool = True) -> list[str]:
    """Names of the files a package would contain, without building it (for previews in the UI)."""
    stem = safe_name(stem)
    wanted = set(artifacts)
    order = [a for a in ("preview", "outline", "legend", "svg", "json", "recipes_png", "mix_preview", "recipes_csv") if a in wanted]
    names = [f"{stem}/{stem}{_SUFFIX[a]}" for a in order]
    return names + ([f"{stem}/package_info.json"] if with_info else [])
