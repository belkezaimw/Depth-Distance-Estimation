"""Tests for configuration loading."""

import os
import pytest
from dfire.utils.config import Config, load_config


class TestConfig:
    def test_default_values_loaded(self):
        cfg = Config()
        assert isinstance(cfg.camera_lat, float)
        assert isinstance(cfg.focal_length_px, float)
        assert cfg.focal_length_px > 0

    def test_as_dict_returns_dict(self):
        cfg = Config()
        d = cfg.as_dict()
        assert isinstance(d, dict)
        assert "camera_lat" in d
        assert "focal_length_px" in d

    def test_update_from_dict(self):
        cfg = Config()
        cfg.update_from_dict({"camera_tilt_deg": -25.0, "max_range_m": 999.0})
        assert cfg.camera_tilt_deg == -25.0
        assert cfg.max_range_m == 999.0

    def test_update_ignores_unknown_keys(self):
        cfg = Config()
        cfg.update_from_dict({"nonexistent_key": 42})  # should not raise

    def test_load_config_overrides(self):
        cfg = load_config(camera_tilt_deg=-30.0, focal_length_px=2000.0)
        assert cfg.camera_tilt_deg == -30.0
        assert cfg.focal_length_px == 2000.0

    def test_load_config_none_overrides_ignored(self):
        cfg_default = load_config()
        cfg_none    = load_config(camera_lat=None)
        assert cfg_default.camera_lat == cfg_none.camera_lat

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DFIRE_MAX_RANGE_M", "12345")
        cfg = Config()
        assert cfg.max_range_m == 12345.0
