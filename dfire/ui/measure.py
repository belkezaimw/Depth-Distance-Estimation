"""
dfire.ui.measure
================
Main measurement window.
Displays the camera image, handles click events, shows ray-cast
and AI-depth distances, and manages the live settings trackbars.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from typing import Optional

import cv2
import numpy as np

from dfire.core.dem     import DEM
from dfire.core.raycast import raycast, RayResult
from dfire.core.depth   import DepthEstimator
from dfire.utils.config  import Config
from dfire.utils.drawing import DrawHelper, P

log = logging.getLogger(__name__)

WIN_MAP = "DFire Distance Estimator"
WIN_CFG = "Live Settings"


class MeasureApp:
    """
    Main measurement application window.

    Parameters
    ----------
    cfg        : populated Config object
    dem        : DEM instance (or None)
    image      : BGR image (numpy array)
    image_path : original file path (for save naming)
    """

    def __init__(
        self,
        cfg:        Config,
        dem:        Optional[DEM],
        image:      np.ndarray,
        image_path: str,
    ) -> None:
        self.cfg    = cfg
        self.dem    = dem
        self.orig   = image
        self.ih, self.iw = image.shape[:2]
        self.base   = os.path.splitext(os.path.basename(image_path))[0]
        self.dh     = DrawHelper(self.iw)

        # Display sizing — use as much screen as possible
        # Allow upscaling small images (DFire 416px) up to 2x for comfort
        MAX_UP   = 2.0   # max upscale factor
        fs_down  = min(1.0, cfg.max_display_w/self.iw, cfg.max_display_h/self.ih)
        fs_up    = min(MAX_UP, cfg.max_display_w/self.iw, cfg.max_display_h/self.ih)
        fs       = fs_up if self.iw < 800 else fs_down
        self.dw  = max(800, int(self.iw * fs))
        self.dh_ = max(600, int(self.ih * fs))
        self.sx  = self.iw / self.dw    # display → image scale X
        self.sy  = self.ih / self.dh_   # display → image scale Y

        # State
        self.result:      Optional[RayResult] = None
        self.hover:       Optional[tuple[int,int]] = None
        self.show_depth:  bool = False
        self.depth_rel:   Optional[np.ndarray] = None   # relative (0-1)
        self.depth_abs:   Optional[np.ndarray] = None   # absolute metres
        self.ai_ready:    bool = False
        self.ai_status:   str  = "Depth Anything V2: loading…"
        self.anchors_px:  list[tuple[int,int]] = []
        self.anchors_dm:  list[float]          = []
        self._de:         Optional[DepthEstimator] = None

        # OpenCV windows
        # WINDOW_KEEPRATIO = OpenCV maintains aspect ratio when user resizes
        # This prevents stretching and keeps the image sharp
        cv2.namedWindow(WIN_MAP, cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(WIN_MAP, self.dw, self.dh_)
        cv2.setMouseCallback(WIN_MAP, self._on_mouse)
        self._open_settings()

        # Load AI in background
        threading.Thread(target=self._load_ai, daemon=True).start()

        log.info("MeasureApp ready — image %dx%d → display %dx%d",
                 self.iw, self.ih, self.dw, self.dh_)
        print("\nControls:  Left-click=measure  D=depth overlay  R=reset  S=save  Q=quit\n")

    # ── AI ─────────────────────────────────────────────────────────────────────

    def _load_ai(self) -> None:
        try:
            self._de = DepthEstimator(
                model_size = self.cfg.ai_model_size,
                cache_dir  = self.cfg.model_cache,
            )
            self.ai_status = "AI: running depth estimation…"
            self.depth_rel = self._de.run(self.orig)
            self.ai_ready  = True
            self.ai_status = "AI: depth ready ✓"
            log.info("Depth map generated ✓")
            self._reanchor()
        except Exception as exc:
            self.ai_status = f"AI error: {exc}"
            log.error("AI depth failed: %s", exc)

    def _reanchor(self) -> None:
        """Rescale depth map to absolute metres using accumulated DEM anchors."""
        if not (self.ai_ready and self.depth_rel is not None and self.anchors_px):
            return
        self.depth_abs = self._de.to_absolute(
            self.depth_rel, self.anchors_px, self.anchors_dm
        )

    # ── settings trackbars ───────────────────────────────────────────────────

    def _open_settings(self) -> None:
        cv2.namedWindow(WIN_CFG, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN_CFG, 520, 280)
        blank = np.full((280, 520, 3), 22, dtype=np.uint8)
        self.dh.text(blank, "DFire Live Settings", 12, 24, P.ACCENT, 0.42, bold=True)
        self.dh.text(blank, "Drag sliders — measurement recalculates instantly", 12, 46, P.GRAY, 0.30)
        cv2.imshow(WIN_CFG, blank)

        def _tb(name: str, cfg_key: str, val: float, maxv: int,
                xf=None, scale: int = 1) -> None:
            init = max(0, min(int(val / scale), maxv))
            def _cb(v: int) -> None:
                raw = v * scale
                setattr(self.cfg, cfg_key, xf(raw) if xf else max(1, raw))
                self._recompute()
            cv2.createTrackbar(name, WIN_CFG, init, maxv, _cb)

        _tb("Cam elev (m ASL)",  "camera_abs_elev_m", self.cfg.camera_abs_elev_m, 2000)
        _tb("Tilt down (deg)",   "camera_tilt_deg",   abs(self.cfg.camera_tilt_deg), 89,
            xf=lambda v: -max(1, v))
        _tb("Focal length (px)", "focal_length_px",   self.cfg.focal_length_px, 5000,
            xf=lambda v: max(50, v))
        _tb("Max range (m)",     "max_range_m",       self.cfg.max_range_m, 15000)
        _tb("Pan bearing (deg)", "camera_pan_deg",    self.cfg.camera_pan_deg, 359,
            xf=lambda v: v)

    def _recompute(self) -> None:
        """Re-run measurement for the current click point after settings change."""
        if self.result and not self.result.is_sky:
            px, py = self.result.pixel
            self.result = self._measure(px, py)
        self._render()

    # ── measurement ───────────────────────────────────────────────────────────

    def _measure(self, px: int, py: int) -> RayResult:
        r = raycast(px, py, self.cfg.as_dict(), self.dem)

        # AI depth distance
        if self.ai_ready and self.depth_abs is not None and not r.is_sky:
            ai_d = self._de.pixel_distance(
                self.depth_abs, px, py,
                self.cfg.camera_abs_elev_m,
                r.pt_elev_m or 0.0,
            )
            r.ai_dist_m = ai_d

        # Accumulate DEM anchors for AI scaling
        if not r.is_sky and r.has_dem and r.dist_3d_m:
            self.anchors_px.append((px, py))
            self.anchors_dm.append(r.dist_3d_m)
            self.anchors_px = self.anchors_px[-10:]
            self.anchors_dm = self.anchors_dm[-10:]
            self._reanchor()

        return r

    # ── mouse ─────────────────────────────────────────────────────────────────

    def _on_mouse(self, ev: int, x: int, y: int, *_) -> None:
        ix = max(0, min(int(x * self.sx), self.iw - 1))
        iy = max(0, min(int(y * self.sy), self.ih - 1))

        if ev == cv2.EVENT_MOUSEMOVE:
            self.hover = (ix, iy)
            if not self.result:
                self._render()

        elif ev == cv2.EVENT_LBUTTONDOWN:
            self.result = self._measure(ix, iy)
            self.hover  = None
            self._log()
            self._render()

    def _log(self) -> None:
        r = self.result
        if r.is_sky:
            print(f"  Pixel {r.pixel} → sky")
            return
        d  = r.dist_3d_m
        ai = r.ai_dist_m
        print(f"\n  Pixel {r.pixel}")
        print(f"    DEM+Ray  : {d:,} m  ({d/1000:.3f} km)")
        if ai:
            print(f"    AI Depth : {ai:,} m  ({ai/1000:.3f} km)")
        print(f"    Horizontal : {r.horiz_m:,} m")
        print(f"    Point elev : {r.pt_elev_m} m ASL")
        print(f"    Elev drop  : {r.elev_diff_m} m")
        print(f"    Ray angle  : {r.el_deg}°")

    # ── rendering ─────────────────────────────────────────────────────────────

    def _render(self) -> None:
        frame = self.orig.copy()
        H, W  = frame.shape[:2]

        # Depth overlay
        if self.show_depth and self.depth_rel is not None:
            cmap = DepthEstimator.colormap(self.depth_rel, alpha=0.50)
            bgr  = cmap[:, :, :3].astype(np.float32)
            a    = cmap[:, :, 3:4].astype(np.float32) / 255.0
            frame = np.clip(frame*(1-a) + bgr*a, 0, 255).astype(np.uint8)

        # Camera marker
        sc     = self.dh.sc
        cam_pt = (W // 2, H - 8)
        cv2.circle(frame, cam_pt, max(5, int(6*sc)), P.PURPLE, -1, cv2.LINE_AA)
        self.dh.text(frame, "CAM",
                     cam_pt[0]-int(14*sc), cam_pt[1]-int(10*sc),
                     P.PURPLE, 0.28*sc)

        # Hover preview
        if self.hover and not self.result:
            hx, hy = self.hover
            cv2.line(frame, cam_pt, (hx, hy), P.BORDER, 1, cv2.LINE_AA)
            cv2.circle(frame, (hx, hy), max(4, int(5*sc)), P.GRAY, 1, cv2.LINE_AA)
            pr = raycast(hx, hy, self.cfg.as_dict(), self.dem)
            if not pr.is_sky and pr.dist_3d_m:
                d  = pr.dist_3d_m
                ds = f"{d/1000:.2f} km" if d >= 1000 else f"{d} m"
                self.dh.badge(frame, ds, hx+12, hy-8, P.BORDER, P.GRAY, 0.34*sc)

        # Measurement result
        if self.result:
            self._draw_result(frame)

        # Status bar
        self.dh.status_bar(
            frame,
            ai_ready  = self.ai_ready,
            dem_on    = self.dem is not None,
            depth_on  = self.show_depth,
        )

        # INTER_LANCZOS4 = best quality for both upscale and downscale
        # Much sharper than INTER_LINEAR, worth the tiny extra CPU cost
        interp = cv2.INTER_AREA if self.dw < W else cv2.INTER_LANCZOS4
        disp   = cv2.resize(frame, (self.dw, self.dh_), interpolation=interp)
        cv2.imshow(WIN_MAP, disp)

    def _draw_result(self, frame: np.ndarray) -> None:
        H, W   = frame.shape[:2]
        r      = self.result
        px, py = r.pixel
        cam_pt = (W // 2, H - 8)
        sc     = self.dh.sc

        if r.is_sky:
            self.dh.crosshair(frame, px, py, (120, 120, 220))
            self.dh.badge(frame, "Sky — no ground here",
                          px+int(14*sc), py-8, (40, 40, 130), P.WHITE, 0.36*sc)
            return

        # Ray line + crosshair
        cv2.line(frame, cam_pt, (px, py), P.ORANGE, max(1, int(sc)), cv2.LINE_AA)
        self.dh.crosshair(frame, px, py, P.ORANGE)

        # Distance badge
        dist = r.dist_3d_m
        ds   = f"{dist/1000:.3f} km" if dist >= 1000 else f"{dist} m"
        lx   = px + int(22*sc) if px < W - int(110*sc) else px - int(120*sc)
        ly   = py - int(22*sc) if py > int(30*sc)      else py + int(28*sc)
        self.dh.badge(frame, ds, lx, ly, P.ORANGE, P.DARK, 0.52*sc)

        # Info panel rows
        ai     = r.ai_dist_m
        ai_ds  = (f"{ai/1000:.3f} km" if ai >= 1000 else f"{ai} m") if ai else None
        conf   = self._de.confidence if (self._de and self._de.is_anchored) else 0.0

        rows = [
            ("Method",     "DEM + Ray cast",                            P.GRAY),
            ("Horizontal", f"{r.horiz_m:,} m",                         P.WHITE),
            ("Point elev", f"{r.pt_elev_m} m ASL",                     P.WHITE),
            ("Elev drop",  f"{r.elev_diff_m} m",                        P.WHITE),
            ("Ray angle",  f"{r.el_deg}°",                              P.WHITE),
            ("Terrain",    "Real DEM ✓" if r.has_dem else "flat",
                           P.GREEN if r.has_dem else P.GRAY),
        ]
        if ai_ds:
            rows.append(("AI Depth", ai_ds, P.YELLOW))

        self.dh.info_panel(
            frame, ds, rows,
            confidence = conf,
            at_max     = bool(r.at_max),
            max_range  = int(self.cfg.max_range_m),
        )

    # ── save ──────────────────────────────────────────────────────────────────

    def save(self) -> None:
        os.makedirs(self.cfg.output_dir, exist_ok=True)
        frame = self.orig.copy()
        if self.result:
            self._draw_result(frame)
        path = os.path.join(self.cfg.output_dir, f"{self.base}_distance.jpg")
        cv2.imwrite(path, frame)
        log.info("Saved → %s", path)
        print(f"  Saved → {path}")

    # ── run loop ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._render()
        while True:
            k = cv2.waitKey(500) & 0xFF
            if k in (ord("q"), ord("Q"), 27):
                break
            elif k in (ord("r"), ord("R")):
                self.result     = None
                self.anchors_px = []
                self.anchors_dm = []
                self.depth_abs  = None
                self._render()
                print("  Reset.")
            elif k in (ord("s"), ord("S")):
                self.save()
            elif k in (ord("d"), ord("D")):
                self.show_depth = not self.show_depth
                self._render()
            else:
                self._render()   # refresh AI status

        cv2.destroyAllWindows()