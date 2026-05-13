"""
dfire.cli
=========
Command-line interface entry point.
Installed as the `dfire` command via pyproject.toml.

Usage examples
--------------
    dfire                                 # launch setup wizard
    dfire run --image cam.jpg             # skip wizard, use .env defaults
    dfire run --image cam.jpg \\
              --dem data/dem/srtm-37-04.tif \\
              --lat 36.73 --lon 2.99 \\
              --elev 14 --tilt -2 --focal 1600
    dfire calibrate --photos calib_photos/
    dfire info                            # show current config from .env
"""

from __future__ import annotations

import logging
import os
import sys

import click
import cv2

from dfire           import __version__
from dfire.core.dem  import DEM
from dfire.ui        import SetupWizard, MeasureApp
from dfire.utils     import load_config, setup_logging

log = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(__version__)
def main(ctx: click.Context) -> None:
    """DFire Distance Estimator — AI + DEM Edition."""
    if ctx.invoked_subcommand is None:
        # No subcommand → launch wizard
        ctx.invoke(wizard)


# ── wizard (default) ─────────────────────────────────────────────────────────

@main.command()
@click.option("--large-ai", is_flag=True, help="Use Depth-Anything-V2-Base (~400 MB)")
@click.option("--log-level", default=None, help="DEBUG | INFO | WARNING")
def wizard(large_ai: bool, log_level: str | None) -> None:
    """Launch the full setup wizard (default command)."""
    cfg = load_config()
    if large_ai:
        cfg.ai_model_size = "base"
    setup_logging(log_level or cfg.log_level)

    print(f"\n  DFire Distance Estimator  v{__version__}")
    print("  Fill in the setup form then click START\n")

    data  = SetupWizard(cfg).run()
    cfg.update_from_dict(data["cfg"].as_dict())

    MeasureApp(cfg, data["dem"], data["image"], data["image_path"]).run()


# ── run (CLI, skip wizard) ───────────────────────────────────────────────────

@main.command()
@click.option("--image",     required=True,  help="Path to camera image")
@click.option("--dem",       default=None,   help="Path to DEM .tif or .hgt")
@click.option("--lat",       type=float, default=None)
@click.option("--lon",       type=float, default=None)
@click.option("--elev",      type=float, default=None, help="Camera elevation m ASL")
@click.option("--tilt",      type=float, default=None, help="Camera tilt degrees")
@click.option("--focal",     type=float, default=None, help="Focal length px")
@click.option("--pan",       type=float, default=None, help="Pan / compass bearing")
@click.option("--range",     "max_range", type=int, default=None, help="Max range m")
@click.option("--large-ai",  is_flag=True,  help="Use larger AI model (~400 MB)")
@click.option("--log-level", default=None)
def run(
    image, dem, lat, lon, elev, tilt, focal, pan, max_range, large_ai, log_level
) -> None:
    """Run measurement directly from CLI arguments (no wizard)."""
    cfg = load_config(
        camera_lat        = lat,
        camera_lon        = lon,
        camera_abs_elev_m = elev,
        camera_tilt_deg   = tilt,
        focal_length_px   = focal,
        camera_pan_deg    = pan,
        max_range_m       = max_range,
    )
    if large_ai:
        cfg.ai_model_size = "base"
    setup_logging(log_level or cfg.log_level)

    img = cv2.imread(image)
    if img is None:
        click.echo(f"ERROR: cannot open image: {image}", err=True)
        sys.exit(1)

    cfg.image_width_px  = img.shape[1]
    cfg.image_height_px = img.shape[0]

    dem_obj = None
    dem_path = dem or cfg.dem_path
    if dem_path and os.path.exists(dem_path):
        dem_obj = DEM(dem_path)
    elif dem_path:
        click.echo(f"WARNING: DEM not found at {dem_path} — using flat ground", err=True)

    MeasureApp(cfg, dem_obj, img, image).run()


# ── calibrate ────────────────────────────────────────────────────────────────

@main.command()
@click.option("--photos",  required=True,  help="Folder of chessboard photos")
@click.option("--output",  default="dfire/camera_params.npz", show_default=True)
@click.option("--cols",    default=7,  show_default=True, help="Inner corners horizontal")
@click.option("--rows",    default=5,  show_default=True, help="Inner corners vertical")
@click.option("--square",  default=30.0, show_default=True, help="Square size in mm")
def calibrate(photos, output, cols, rows, square) -> None:
    """Calibrate camera focal length using chessboard photos."""
    import glob
    import numpy as np

    setup_logging()
    pattern = (cols, rows)
    obj_pt  = np.zeros((cols*rows, 3), np.float32)
    obj_pt[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square

    obj_pts, img_pts = [], []
    paths = sorted(
        glob.glob(os.path.join(photos, "*.jpg")) +
        glob.glob(os.path.join(photos, "*.png"))
    )
    if not paths:
        click.echo(f"No .jpg/.png found in {photos}", err=True)
        sys.exit(1)

    img_size = None
    found = 0
    for p in paths:
        img  = cv2.imread(p)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_size = gray.shape[::-1]
        ret, corners = cv2.findChessboardCorners(gray, pattern, None)
        if ret:
            found += 1
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners = cv2.cornerSubPix(gray, corners, (11,11), (-1,-1), crit)
            obj_pts.append(obj_pt)
            img_pts.append(corners)
            click.echo(f"  ✓  {os.path.basename(p)}")
        else:
            click.echo(f"  ✗  {os.path.basename(p)} (not found)")

    if found < 5:
        click.echo(f"\nNeed ≥5 detections (got {found}). Retake photos.", err=True)
        sys.exit(1)

    click.echo(f"\nCalibrating from {found} images…")
    ret, K, dist, _, _ = cv2.calibrateCamera(obj_pts, img_pts, img_size, None, None)
    fx, fy = K[0,0], K[1,1]
    cx, cy = K[0,2], K[1,2]
    click.echo(f"  Focal X : {fx:.1f} px")
    click.echo(f"  Focal Y : {fy:.1f} px")
    click.echo(f"  Centre  : ({cx:.1f}, {cy:.1f})")

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    np.savez(output, K=K, dist=dist, img_size=img_size)
    click.echo(f"\n  Saved → {output}")
    click.echo(f"\nSet DFIRE_FOCAL_LENGTH_PX={(fx+fy)/2:.0f} in your .env file")


# ── info ─────────────────────────────────────────────────────────────────────

@main.command()
def info() -> None:
    """Show current configuration loaded from .env / environment."""
    setup_logging("WARNING")
    cfg = load_config()
    click.echo(f"\nDFire v{__version__} — current config\n")
    for k, v in cfg.as_dict().items():
        click.echo(f"  {k:<26} {v}")
    click.echo()
