"""
dfire.core.depth
================
Depth Anything V2 wrapper.

The model outputs RELATIVE depth (disparity: higher value = closer).
We convert to ABSOLUTE metres by anchoring against DEM ray cast distances:

    scale = median(dem_dist × relative_depth_at_pixel)
    abs_dist(px) = scale / relative_depth(px)

The more DEM anchors you provide (by clicking known points),
the more accurate the absolute scaling becomes.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

_MODELS = {
    "small": "depth-anything/Depth-Anything-V2-Small-hf",   # ~100 MB
    "base":  "depth-anything/Depth-Anything-V2-Base-hf",    # ~400 MB
    "large": "depth-anything/Depth-Anything-V2-Large-hf",   # ~1.3 GB
}


class DepthEstimator:
    """
    Wraps Depth Anything V2 for per-pixel distance estimation.

    Parameters
    ----------
    model_size : "small" | "base" | "large"
    cache_dir  : where to store downloaded model weights
    device     : "cpu" | "cuda" | "auto"

    Example
    -------
    >>> de = DepthEstimator(model_size="small")
    >>> depth = de.run(image_bgr)                  # relative depth HxW
    >>> abs_m = de.to_absolute(depth, [(px,py)], [dem_dist_m])
    >>> dist  = de.pixel_distance(abs_m, px, py)
    """

    def __init__(
        self,
        model_size: str = "small",
        cache_dir:  str = "models/",
        device:     str = "auto",
    ) -> None:
        import torch
        from transformers import pipeline as hf_pipeline

        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        model_id = _MODELS.get(model_size, _MODELS["small"])
        log.info("Loading Depth Anything V2 (%s) on %s …", model_size, self.device)

        self._pipe = hf_pipeline(
            task      = "depth-estimation",
            model     = model_id,
            device    = self.device,
            cache_dir = cache_dir,
        )

        self._scale    = 1.0
        self._anchored = False
        self._n_anchors = 0

        log.info("Depth model ready ✓")

    # ── inference ─────────────────────────────────────────────────────────────

    def run(self, image_bgr: np.ndarray) -> np.ndarray:
        """
        Run depth estimation on a BGR OpenCV image.

        Returns
        -------
        depth_map : np.ndarray float32, shape (H, W)
            Normalised relative depth in [0, 1].
            Higher value = closer to camera (disparity convention).
        """
        h, w = image_bgr.shape[:2]
        rgb  = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil  = Image.fromarray(rgb)

        result = self._pipe(pil)
        raw    = np.array(result["depth"], dtype=np.float32)

        if raw.shape != (h, w):
            raw = cv2.resize(raw, (w, h), interpolation=cv2.INTER_LINEAR)

        # Normalise to [0, 1]
        d_min, d_max = raw.min(), raw.max()
        if d_max > d_min:
            raw = (raw - d_min) / (d_max - d_min)

        log.debug("Depth map generated: shape=%s  min=%.3f max=%.3f",
                  raw.shape, raw.min(), raw.max())
        return raw

    # ── absolute scaling ──────────────────────────────────────────────────────

    def to_absolute(
        self,
        depth_map:     np.ndarray,
        anchor_pixels: list[tuple[int, int]],
        anchor_dists:  list[float],
    ) -> np.ndarray:
        """
        Scale relative depth map to absolute metres.

        Uses the relationship:  abs_dist = scale / disparity
        Fits scale via: scale = median(anchor_dist × anchor_disparity)

        Parameters
        ----------
        depth_map     : relative depth (H×W float32, [0,1])
        anchor_pixels : list of (px, py) image coordinates
        anchor_dists  : list of real distances in metres (from DEM raycast)

        Returns
        -------
        abs_map : np.ndarray float32 (H×W) — metres per pixel
        """
        if not anchor_pixels:
            return depth_map.copy()

        h, w   = depth_map.shape
        scales = []

        for (px, py), dist_m in zip(anchor_pixels, anchor_dists):
            px = max(0, min(int(px), w - 1))
            py = max(0, min(int(py), h - 1))
            d  = float(depth_map[py, px])
            if d > 0.01 and dist_m > 0.5:
                scales.append(dist_m * d)

        if scales:
            self._scale     = float(np.median(scales))
            self._anchored  = True
            self._n_anchors = len(scales)
            log.info("Depth anchored: scale=%.1f  n=%d anchors",
                     self._scale, self._n_anchors)
        else:
            log.warning("No valid anchors — depth not scaled")

        safe  = np.where(depth_map > 1e-4, depth_map, 1e-4)
        return (self._scale / safe).astype(np.float32)

    def pixel_distance(
        self,
        abs_map:   np.ndarray,
        px: int,   py: int,
        cam_elev:  float,
        pt_elev:   float,
    ) -> Optional[float]:
        """
        Return absolute 3D distance for a pixel from the scaled depth map.
        Returns None if the map is not anchored.
        """
        if not self._anchored:
            return None
        h, w = abs_map.shape
        px = max(0, min(int(px), w - 1))
        py = max(0, min(int(py), h - 1))
        horiz = float(abs_map[py, px])
        if horiz < 0.1:
            return None
        elev_diff = abs(cam_elev - pt_elev)
        return round(math.sqrt(horiz ** 2 + elev_diff ** 2))

    @property
    def confidence(self) -> float:
        """Rough confidence 0–1 based on number of anchors (saturates at 10)."""
        return min(1.0, self._n_anchors / 10.0)

    @property
    def is_anchored(self) -> bool:
        return self._anchored

    # ── visualisation ─────────────────────────────────────────────────────────

    @staticmethod
    def colormap(depth_map: np.ndarray, alpha: float = 0.50) -> np.ndarray:
        """
        Convert relative depth map to a BGRA overlay.
        Warm colours (yellow/white) = near, cool (purple/black) = far.
        """
        norm = depth_map.copy()
        mn, mx = norm.min(), norm.max()
        if mx > mn:
            norm = (norm - mn) / (mx - mn)
        heat  = (norm * 255).astype(np.uint8)
        color = cv2.applyColorMap(heat, cv2.COLORMAP_INFERNO)
        a_ch  = np.full((*heat.shape, 1), int(alpha * 255), dtype=np.uint8)
        return np.concatenate([color, a_ch], axis=-1)
