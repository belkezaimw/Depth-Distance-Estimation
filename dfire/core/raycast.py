"""
dfire.core.raycast
==================
Geometric ray casting: pixel → real-world distance via DEM terrain lookup.

Pipeline per click
------------------
1. pixel (px, py)
   → elevation angle  = camera_tilt − atan2(py − cy, focal)
   → horizontal bearing = camera_pan + atan2(px − cx, focal)

2. March along the ray in steps of max_range/STEPS metres.
   At each step compute:
       ray_elevation   = cam_abs_elev + tan(el_angle) × horiz_dist
       terrain_elev    = DEM.elevation(lat, lon)   [or flat floor]

3. When ray_elevation ≤ terrain_elevation → interpolate sub-step hit point.

4. dist_3d = √(horiz² + elev_diff²)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from .dem import DEM, geo_move

log = logging.getLogger(__name__)

STEPS = 3_000   # march resolution


@dataclass
class RayResult:
    """All information about a single ray cast."""
    pixel:      tuple[int, int]
    is_sky:     bool  = False

    # geometry
    el_deg:     float = 0.0
    bearing_deg: float = 0.0

    # distances (None if is_sky)
    dist_3d_m:  Optional[float] = None
    horiz_m:    Optional[float] = None
    pt_elev_m:  Optional[float] = None
    cam_elev_m: Optional[float] = None
    elev_diff_m: Optional[float] = None

    # flags
    has_dem:    bool  = False
    at_max:     bool  = False

    # AI result (filled later by MeasureApp)
    ai_dist_m:  Optional[float] = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def pixel_to_ray(px: int, py: int, cfg: dict) -> tuple[float, float]:
    """
    Convert image pixel to (elevation_angle_deg, bearing_deg).

    elevation_angle_deg < 0  → looking downward  (will hit ground)
    elevation_angle_deg ≥ 0  → looking at sky
    """
    W, H  = cfg["image_width_px"], cfg["image_height_px"]
    f     = cfg["focal_length_px"]
    tilt  = -abs(float(cfg["camera_tilt_deg"]))
    pan   = float(cfg.get("camera_pan_deg", 0.0))

    el_deg  = tilt - math.degrees(math.atan2(py - H / 2.0, f))
    bearing = (pan + math.degrees(math.atan2(px - W / 2.0, f))) % 360.0
    return el_deg, bearing


def raycast(px: int, py: int, cfg: dict, dem: Optional[DEM]) -> RayResult:
    """
    Cast a ray from the camera through pixel (px, py).

    Parameters
    ----------
    px, py   : pixel coordinates in the original image
    cfg      : camera configuration dict (see config.py)
    dem      : DEM instance for terrain lookup, or None for flat ground

    Returns
    -------
    RayResult dataclass
    """
    el_deg, bearing = pixel_to_ray(px, py, cfg)

    cam_e   = float(cfg["camera_abs_elev_m"])
    max_r   = float(cfg["max_range_m"])
    lat0    = float(cfg["camera_lat"])
    lon0    = float(cfg["camera_lon"])
    floor_e = float(cfg.get("valley_floor_m", 0.0))

    base = RayResult(
        pixel       = (px, py),
        el_deg      = round(el_deg, 2),
        bearing_deg = round(bearing, 1),
        cam_elev_m  = round(cam_e),
        has_dem     = dem is not None,
    )

    if el_deg >= -0.05:
        base.is_sky = True
        log.debug("Pixel (%d,%d) points at sky (el=%.2f°)", px, py, el_deg)
        return base

    el_rad = math.radians(el_deg)
    step   = max_r / STEPS
    prev_c = None
    hit_h  = max_r
    hit_e  = floor_e

    for i in range(1, STEPS + 1):
        horiz  = i * step
        ray_e  = cam_e + math.tan(el_rad) * horiz

        if dem:
            lt, ln = geo_move(lat0, lon0, bearing, horiz)
            terr_e = dem.elevation(lt, ln)
        else:
            terr_e = floor_e

        clearance = ray_e - terr_e

        if clearance <= 0 and prev_c is not None and prev_c > 0:
            # Sub-step linear interpolation
            frac  = prev_c / (prev_c - clearance)
            hit_h = horiz - (1.0 - frac) * step
            if dem:
                lt, ln = geo_move(lat0, lon0, bearing, hit_h)
                hit_e  = dem.elevation(lt, ln)
            else:
                hit_e = floor_e
            break

        prev_c = clearance

    elev_diff = cam_e - hit_e
    dist_3d   = math.sqrt(hit_h ** 2 + elev_diff ** 2)

    base.dist_3d_m  = round(dist_3d)
    base.horiz_m    = round(hit_h)
    base.pt_elev_m  = round(hit_e)
    base.elev_diff_m = round(elev_diff)
    base.at_max     = hit_h >= max_r - step

    log.debug(
        "Raycast (%d,%d) → %.0f m (horiz=%.0f m, el=%.1f°, dem=%s)",
        px, py, dist_3d, hit_h, el_deg, dem is not None,
    )
    return base
