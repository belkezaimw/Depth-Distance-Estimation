"""
dfire.utils.config
==================
Loads configuration from .env file, then environment variables,
with a typed Config dataclass as the result.

Priority (highest first):
    1. CLI arguments (handled in cli.py)
    2. Environment variables (set manually or via .env)
    3. Defaults defined here
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()          # reads .env into os.environ if present
except ImportError:
    pass                   # python-dotenv is optional; env vars still work


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)

def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))

def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


@dataclass
class Config:
    """Typed camera + application configuration."""

    # ── camera geometry ───────────────────────────────────────────────────────
    camera_lat:        float = field(default_factory=lambda: _env_float("DFIRE_CAMERA_LAT",  36.731627))
    camera_lon:        float = field(default_factory=lambda: _env_float("DFIRE_CAMERA_LON",   2.994820))
    camera_abs_elev_m: float = field(default_factory=lambda: _env_float("DFIRE_CAMERA_ELEV_M", 14.0))
    camera_tilt_deg:   float = field(default_factory=lambda: _env_float("DFIRE_CAMERA_TILT_DEG", -2.0))
    camera_pan_deg:    float = field(default_factory=lambda: _env_float("DFIRE_CAMERA_PAN_DEG",   0.0))
    focal_length_px:   float = field(default_factory=lambda: _env_float("DFIRE_FOCAL_LENGTH_PX", 1600.0))
    max_range_m:       float = field(default_factory=lambda: _env_float("DFIRE_MAX_RANGE_M",  6000.0))
    valley_floor_m:    float = field(default_factory=lambda: _env_float("DFIRE_VALLEY_FLOOR_M",  0.0))

    # ── image (filled at runtime) ─────────────────────────────────────────────
    image_width_px:  int = 0
    image_height_px: int = 0

    # ── files ─────────────────────────────────────────────────────────────────
    dem_path:     str = field(default_factory=lambda: _env("DFIRE_DEM_PATH",    "data/dem/"))
    model_cache:  str = field(default_factory=lambda: _env("DFIRE_MODEL_CACHE", "models/"))
    output_dir:   str = field(default_factory=lambda: _env("DFIRE_OUTPUT_DIR",  "output/"))

    # ── AI ────────────────────────────────────────────────────────────────────
    ai_model_size: str = field(default_factory=lambda: _env("DFIRE_AI_MODEL_SIZE", "small"))

    # ── display ───────────────────────────────────────────────────────────────
    max_display_w: int = field(default_factory=lambda: _env_int("DFIRE_MAX_DISPLAY_W", 1600))
    max_display_h: int = field(default_factory=lambda: _env_int("DFIRE_MAX_DISPLAY_H",  920))

    # ── logging ───────────────────────────────────────────────────────────────
    log_level: str = field(default_factory=lambda: _env("DFIRE_LOG_LEVEL", "INFO"))

    def as_dict(self) -> dict:
        """Return as plain dict (compatible with raycast / DEM calls)."""
        return self.__dict__.copy()

    def update_from_dict(self, d: dict) -> None:
        """Update fields from a plain dict (e.g. from the setup wizard)."""
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, v)


def load_config(**overrides) -> Config:
    """
    Load config from environment / .env, then apply any keyword overrides.

    Example
    -------
    >>> cfg = load_config(camera_tilt_deg=-15, max_range_m=8000)
    """
    cfg = Config()
    for k, v in overrides.items():
        if v is not None and hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg
