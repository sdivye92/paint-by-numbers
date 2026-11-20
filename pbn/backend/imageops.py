"""Image loading, edge-preserving smoothing and colour-space helpers."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_image(path: str | Path, size: int = 800) -> np.ndarray:
    """Load an image as RGB uint8, downscaled so its long side is at most `size`."""
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)  # applies EXIF orientation
    if bgr is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return _prepare(bgr, size)


def load_image_bytes(data: bytes, size: int = 800) -> np.ndarray:
    """Same as load_image, for encoded image bytes (e.g. a file uploaded in the web app)."""
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode image data")
    return _prepare(bgr, size)


def _prepare(bgr: np.ndarray, size: int) -> np.ndarray:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    scale = size / max(h, w)
    if scale < 1:
        rgb = cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return rgb


def smooth(rgb: np.ndarray, iters: int = 3, sigma_color: float = 35, sigma_space: float = 7) -> np.ndarray:
    """Edge-preserving smoothing (repeated bilateral filter).

    Flattens texture and sensor noise inside regions while keeping real edges,
    which is what stops the quantiser from producing thousands of speckles.
    """
    out = rgb
    for _ in range(iters):
        out = cv2.bilateralFilter(out, 9, sigma_color, sigma_space)
    return out


def rgb2lab(rgb: np.ndarray) -> np.ndarray:
    """uint8 RGB (H,W,3) -> float32 CIELAB (L in 0..100)."""
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)


def lab2rgb(lab: np.ndarray) -> np.ndarray:
    """float CIELAB (N,3) -> uint8 RGB (N,3)."""
    flat = np.ascontiguousarray(lab, dtype=np.float32).reshape(-1, 1, 3)
    rgb = cv2.cvtColor(flat, cv2.COLOR_Lab2RGB).reshape(-1, 3)
    return np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
