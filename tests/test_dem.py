"""Tests for DEM loader and elevation lookup."""

import math
import os
import tempfile

import numpy as np
import pytest

from dfire.core.dem import DEM, geo_move


class TestGeoMove:
    def test_north_increases_lat(self):
        lat, lon = geo_move(36.0, 3.0, 0, 1000)
        assert lat > 36.0
        assert abs(lon - 3.0) < 0.001

    def test_east_increases_lon(self):
        lat, lon = geo_move(36.0, 3.0, 90, 1000)
        assert lon > 3.0
        assert abs(lat - 36.0) < 0.001

    def test_1km_north_approx_0009_deg(self):
        lat, _ = geo_move(36.0, 3.0, 0, 1000)
        delta = lat - 36.0
        assert 0.008 < delta < 0.010   # ~0.009° per km

    def test_zero_distance_returns_same(self):
        lat, lon = geo_move(36.5, 2.5, 45, 0)
        assert abs(lat - 36.5) < 1e-9
        assert abs(lon - 2.5) < 1e-9


class TestDEMSynthetic:
    """Test DEM using a synthetic .hgt file written to a temp directory."""

    @pytest.fixture
    def hgt_path(self, tmp_path):
        n = 1201   # SRTM3
        data = np.full((n, n), 200, dtype=">i2")
        # Add a hill in the middle
        r0, c0 = n//2, n//2
        for dr in range(-50, 51):
            for dc in range(-50, 51):
                r, c = r0+dr, c0+dc
                if 0 <= r < n and 0 <= c < n:
                    h = int(200 + 300 * math.exp(-(dr**2+dc**2)/500))
                    data[r, c] = h
        path = tmp_path / "N36E002.hgt"
        data.tofile(str(path))
        return str(path)

    def test_loads_without_error(self, hgt_path):
        dem = DEM(hgt_path)
        assert dem.n_rows == 1201
        assert dem.n_cols == 1201

    def test_coverage_correct(self, hgt_path):
        dem = DEM(hgt_path)
        assert dem.lat_bot == 36
        assert dem.lat_top == 37
        assert dem.lon0    == 2

    def test_elevation_in_range(self, hgt_path):
        dem = DEM(hgt_path)
        e = dem.elevation(36.5, 2.5)
        assert 100 <= e <= 600

    def test_outside_tile_returns_zero(self, hgt_path):
        dem = DEM(hgt_path)
        e = dem.elevation(10.0, 10.0)   # far outside N36E002
        assert e == 0.0

    def test_bilinear_smooth(self, hgt_path):
        """Bilinear interpolation: elevation should vary smoothly."""
        dem = DEM(hgt_path)
        e1 = dem.elevation(36.30, 2.30)
        e2 = dem.elevation(36.31, 2.30)
        # Should differ by less than 50 m between 0.01° steps
        assert abs(e1 - e2) < 50

    def test_profile_returns_correct_count(self, hgt_path):
        dem = DEM(hgt_path)
        prof = dem.profile(36.5, 2.5, 0, 1000, steps=10)
        assert len(prof) == 11   # steps+1

    def test_unsupported_format_raises(self, tmp_path):
        bad = tmp_path / "file.xyz"
        bad.write_bytes(b"\x00" * 100)
        with pytest.raises(ValueError, match="Unsupported"):
            DEM(str(bad))

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            DEM("/nonexistent/path/N00E000.hgt")
