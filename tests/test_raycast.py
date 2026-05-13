"""Tests for the ray casting engine."""

import math
import pytest
from dfire.core.raycast import raycast, pixel_to_ray, RayResult


BASE_CFG = {
    "camera_lat":        36.731627,
    "camera_lon":        2.994820,
    "camera_abs_elev_m": 14.0,
    "camera_tilt_deg":   -2.0,
    "focal_length_px":   1600.0,
    "camera_pan_deg":    0.0,
    "max_range_m":       6000.0,
    "valley_floor_m":    0.0,
    "image_width_px":    2448,
    "image_height_px":   3264,
}


class TestPixelToRay:
    def test_centre_pixel_equals_tilt(self):
        """Centre pixel should point exactly at the tilt angle."""
        cfg = BASE_CFG.copy()
        W, H = cfg["image_width_px"], cfg["image_height_px"]
        el, _ = pixel_to_ray(W // 2, H // 2, cfg)
        assert abs(el - cfg["camera_tilt_deg"]) < 0.1

    def test_below_centre_more_negative(self):
        """Pixels below centre should have a more negative elevation angle."""
        cfg = BASE_CFG.copy()
        W, H = cfg["image_width_px"], cfg["image_height_px"]
        el_mid,   _ = pixel_to_ray(W//2, H//2,     cfg)
        el_lower, _ = pixel_to_ray(W//2, H//2+200, cfg)
        assert el_lower < el_mid

    def test_sky_above_centre(self):
        """Pixels well above centre should produce sky results."""
        cfg = BASE_CFG.copy()
        W = cfg["image_width_px"]
        el, _ = pixel_to_ray(W//2, 100, cfg)
        assert el > 0


class TestRaycast:
    def test_sky_pixel_returns_is_sky(self):
        r = raycast(1224, 100, BASE_CFG, dem=None)
        assert r.is_sky is True
        assert r.dist_3d_m is None

    def test_ground_pixel_returns_distance(self):
        r = raycast(1224, 3000, BASE_CFG, dem=None)
        assert r.is_sky is False
        assert r.dist_3d_m is not None
        assert r.dist_3d_m > 0

    def test_lower_pixel_closer_than_upper(self):
        """Pixels lower in the image (more downward angle) = shorter distance."""
        r_near = raycast(1224, 3100, BASE_CFG, dem=None)
        r_far  = raycast(1224, 2000, BASE_CFG, dem=None)
        assert not r_near.is_sky
        assert not r_far.is_sky
        assert r_near.dist_3d_m < r_far.dist_3d_m

    def test_distance_is_positive(self):
        for py in [2000, 2500, 3000, 3200]:
            r = raycast(1224, py, BASE_CFG, dem=None)
            if not r.is_sky:
                assert r.dist_3d_m > 0

    def test_distance_3d_geq_horizontal(self):
        """3D distance must always be ≥ horizontal distance."""
        r = raycast(1224, 2500, BASE_CFG, dem=None)
        if not r.is_sky:
            assert r.dist_3d_m >= r.horiz_m

    def test_result_is_ray_result_instance(self):
        r = raycast(1224, 2500, BASE_CFG, dem=None)
        assert isinstance(r, RayResult)

    def test_known_approximate_distance(self):
        """People on pavement at py≈2800 should be ~15–35 m away."""
        r = raycast(1224, 2800, BASE_CFG, dem=None)
        assert not r.is_sky
        assert 10 <= r.dist_3d_m <= 50

    def test_pixel_stored_in_result(self):
        r = raycast(500, 2000, BASE_CFG, dem=None)
        assert r.pixel == (500, 2000)

    def test_no_dem_has_dem_false(self):
        r = raycast(1224, 2500, BASE_CFG, dem=None)
        assert r.has_dem is False
