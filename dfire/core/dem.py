"""
dfire.core.dem
==============
Digital Elevation Model loader and elevation lookup.

Supported formats:
    .tif / .tiff  — GeoTIFF (CGIAR SRTM, Copernicus DEM, etc.)
    .hgt          — NASA SRTM binary (N36E002.hgt etc.)
    .img          — ERDAS Imagine (some SRTM distributions)
"""

from __future__ import annotations

import logging
import math
import os

import numpy as np

log = logging.getLogger(__name__)

EARTH_R = 6_371_000.0  # metres


class DEM:
    """
    Loads a DEM file and provides fast bilinear-interpolated
    elevation lookup by GPS coordinate.

    Example
    -------
    >>> dem = DEM("data/dem/srtm-37-04.tif")
    >>> dem.elevation(36.73, 2.99)
    142.3
    """

    def __init__(self, path: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(f"DEM file not found: {path}")

        ext = os.path.splitext(path)[1].lower()
        if ext in (".tif", ".tiff", ".img"):
            self._load_tif(path)
        elif ext == ".hgt":
            self._load_hgt(path)
        else:
            raise ValueError(f"Unsupported DEM format '{ext}'. Use .tif or .hgt")

        log.info(
            "DEM loaded: %s  %dx%d  ~%.0f m/px  lat %.2f–%.2f  lon %.2f–%.2f",
            os.path.basename(path),
            self.n_rows, self.n_cols,
            self.res_deg * 111_000,
            self.lat_bot, self.lat_top,
            self.lon0, self.lon0 + self.n_cols * self.res_deg,
        )

    # ── loaders ───────────────────────────────────────────────────────────────

    def _load_tif(self, path: str) -> None:
        try:
            import rasterio
        except ImportError as e:
            raise ImportError("Install rasterio:  pip install rasterio") from e

        with rasterio.open(path) as ds:
            self.data    = ds.read(1).astype(np.float32)
            self.data[self.data < -1_000] = 0.0   # void fill
            t            = ds.transform
            self.lon0    = float(t.c)
            self.lat_top = float(t.f)
            self.lat_bot = float(t.f + t.e * ds.height)
            self.n_rows  = ds.height
            self.n_cols  = ds.width
            self.res_deg = float(abs(t.a))

    def _load_hgt(self, path: str) -> None:
        size = os.path.getsize(path)
        if size == 2 * 1201 * 1201:
            n = 1201   # SRTM3 ~90 m
        elif size == 2 * 3601 * 3601:
            n = 3601   # SRTM1 ~30 m
        else:
            raise ValueError(
                f"Unexpected .hgt size {size}. "
                "Expected SRTM1 (25,934,402 B) or SRTM3 (2,884,802 B)."
            )

        fname    = os.path.basename(path).upper()
        lat_hem  = fname[0];  lat_val = int(fname[1:3])
        lon_hem  = fname[3];  lon_val = int(fname[4:7])
        lat_bot  = lat_val if lat_hem == "N" else -lat_val
        lon0     = lon_val if lon_hem == "E" else -lon_val

        raw = np.fromfile(path, dtype=">i2").reshape((n, n))
        raw[raw == -32768] = 0

        self.data    = raw.astype(np.float32)
        self.lat_bot = float(lat_bot)
        self.lat_top = float(lat_bot + 1.0)
        self.lon0    = float(lon0)
        self.n_rows  = n
        self.n_cols  = n
        self.res_deg = 1.0 / (n - 1)

    # ── public API ────────────────────────────────────────────────────────────

    def elevation(self, lat: float, lon: float) -> float:
        """
        Return terrain elevation (metres ASL) at (lat, lon).
        Uses bilinear interpolation. Returns 0.0 if outside tile.
        """
        row_f = (self.lat_top - lat) / self.res_deg
        col_f = (lon - self.lon0)    / self.res_deg

        if not (0.0 <= row_f <= self.n_rows - 1 and
                0.0 <= col_f <= self.n_cols - 1):
            log.debug("DEM miss: lat=%.4f lon=%.4f outside tile", lat, lon)
            return 0.0

        r0, c0 = int(row_f), int(col_f)
        r1 = min(r0 + 1, self.n_rows - 1)
        c1 = min(c0 + 1, self.n_cols - 1)
        dr, dc = row_f - r0, col_f - c0

        return float(
            self.data[r0, c0] * (1 - dr) * (1 - dc)
            + self.data[r0, c1] * (1 - dr) * dc
            + self.data[r1, c0] * dr       * (1 - dc)
            + self.data[r1, c1] * dr       * dc
        )

    def profile(
        self,
        lat0: float,
        lon0: float,
        bearing_deg: float,
        max_dist_m: float,
        steps: int = 300,
    ) -> list[tuple[float, float]]:
        """
        Return [(dist_m, elevation_m), ...] along a ray from (lat0, lon0).
        Useful for visualising terrain cross-sections.
        """
        result = []
        for i in range(steps + 1):
            d = i / steps * max_dist_m
            lt, ln = geo_move(lat0, lon0, bearing_deg, d)
            result.append((d, self.elevation(lt, ln)))
        return result


# ── geo helpers ───────────────────────────────────────────────────────────────

def geo_move(
    lat: float, lon: float, bearing_deg: float, dist_m: float
) -> tuple[float, float]:
    """
    Move dist_m metres along bearing_deg from (lat, lon).
    Uses flat-earth approximation — accurate to <0.05 % within 20 km.
    """
    b    = math.radians(bearing_deg)
    dlat = dist_m * math.cos(b) / EARTH_R
    dlon = dist_m * math.sin(b) / (EARTH_R * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)
