# DFire Distance Estimator

> Click any point in a surveillance camera image and get the real-world distance from the camera — powered by geometric ray casting, SRTM terrain data, and Depth Anything V2 AI.

---

## Table of contents

- [Overview](#overview)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project structure](#project-structure)
- [Running tests](#running-tests)
- [Camera calibration](#camera-calibration)
- [DEM data](#dem-data)
- [Accuracy](#accuracy)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

DFire Distance Estimator is a desktop computer vision tool designed for fixed surveillance cameras — particularly those used in wildfire detection systems such as the [DFire dataset](https://github.com/gaiasd/DFireDataset). Given a camera image, you fill in the camera parameters once, then click any visible point to instantly receive its distance from the camera in metres.

Two independent methods run simultaneously and are shown side by side:

| Method | Description | Typical accuracy |
|--------|-------------|-----------------|
| **DEM + Ray casting** | Geometric ray shot through the clicked pixel, checked against real SRTM terrain elevation | ±10–30 m |
| **AI depth (Depth Anything V2)** | Neural network estimates per-pixel depth, calibrated to real metres using DEM anchors | ±5–15 m after 5+ clicks |

---

## How it works

```
Camera image + camera parameters
        │
        ▼
┌───────────────────────────────────────────────┐
│              Setup wizard                     │
│  GPS · elevation · tilt · focal · DEM file   │
└───────────────────────┬───────────────────────┘
                        │
                        ▼
        ┌───────────────────────────┐
        │    Measurement window     │
        │  You click a pixel (x,y)  │
        └──────────┬────────────────┘
                   │
        ┌──────────┴────────────────┐
        │                           │
        ▼                           ▼
 DEM + Ray casting          Depth Anything V2
 ─────────────────          ────────────────
 pixel → elevation angle    Whole-image depth map
 ray marches forward        Relative → absolute metres
 checks terrain height      via DEM anchor calibration
 at each step               (improves with each click)
        │                           │
        └──────────┬────────────────┘
                   ▼
         Distance result shown on screen
```

### Ray casting in detail

1. The clicked pixel is converted to an elevation angle using focal length and tilt.
2. A ray is cast from the camera GPS position at that angle and compass bearing.
3. The ray advances in 3 000 steps up to the configured max range.
4. At each step the real terrain elevation is looked up from the DEM file.
5. When the ray elevation drops below the terrain elevation, the hit point is interpolated.
6. `distance_3d = √(horizontal² + elevation_drop²)`

### AI depth calibration

Depth Anything V2 produces a relative depth map (higher value = closer). To convert to real metres:

```
scale  = median(DEM_distance × depth_value)   # computed from all anchor clicks
abs_m  = scale / depth_value                  # applied to every pixel
```

The more points you click while the DEM is active, the more accurate the AI calibration becomes. A confidence bar in the UI fills as anchors accumulate.

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or higher |
| Operating system | Windows 10/11, Linux, macOS |
| RAM | 4 GB minimum, 8 GB recommended |
| Disk space | ~600 MB (AI model + DEM file) |
| Internet | Required on first run to download the AI model (~100 MB) |

---

## Installation

### Windows

```bat
git clone https://github.com/yourname/dfire-estimator.git
cd dfire-estimator
scripts\setup_env.bat
```

### Linux / macOS

```bash
git clone https://github.com/yourname/dfire-estimator.git
cd dfire-estimator
bash scripts/setup_env.sh
```

The setup script creates a `.venv/` virtual environment, installs all dependencies, and copies `.env.example` to `.env`.

### Manual installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
cp .env.example .env
```

---

## Quick start

```bash
# 1. Activate the environment
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Edit .env with your camera parameters
# 3. Put your DEM file in data/dem/

# 4. Launch
dfire
```

The setup wizard opens. Fill in your camera parameters, browse for your DEM file and image, then click **START**.

---

## Configuration

Copy `.env.example` to `.env` and edit it. All values can also be passed as CLI arguments.

```ini
# Camera GPS position
DFIRE_CAMERA_LAT=36.731627       # latitude  (decimal degrees, N = positive)
DFIRE_CAMERA_LON=2.994820        # longitude (decimal degrees, E = positive)
DFIRE_CAMERA_ELEV_M=14           # elevation above sea level (metres)
                                  # = ground elevation at site + floor/pole height

# Camera orientation
DFIRE_CAMERA_TILT_DEG=-2         # vertical tilt — negative = looking down
DFIRE_CAMERA_PAN_DEG=0           # compass bearing: 0=North, 90=East, 180=South

# Optics
DFIRE_FOCAL_LENGTH_PX=1600       # focal length in pixels (run: dfire calibrate)

# Terrain
DFIRE_DEM_PATH=data/dem/srtm-37-04.tif
DFIRE_MAX_RANGE_M=6000           # maximum search distance in metres
DFIRE_VALLEY_FLOOR_M=0           # minimum terrain elevation in scene (metres ASL)

# AI model
DFIRE_AI_MODEL_SIZE=small        # small (~100 MB) or base (~400 MB, more accurate)
DFIRE_MODEL_CACHE=models/

# Output
DFIRE_OUTPUT_DIR=output/
DFIRE_LOG_LEVEL=INFO
```

### How to measure each parameter

| Parameter | Method |
|-----------|--------|
| `CAMERA_LAT` / `LON` | Google Maps — long press your camera location, copy the coordinates |
| `CAMERA_ELEV_M` | Google Earth — paste coordinates, read elevation at bottom. Add floor/pole height. |
| `CAMERA_TILT_DEG` | Free inclinometer app on phone. Hold phone against camera body. Value will be negative. |
| `CAMERA_PAN_DEG` | Compass app. Stand behind the camera and read the bearing it faces. |
| `FOCAL_LENGTH_PX` | Run `dfire calibrate --photos folder/` or check camera spec sheet. |

---

## Usage

### Setup wizard (default)

```bash
dfire
```

Opens the graphical setup form pre-filled from your `.env` file. Use **Browse** to pick your DEM and image files. Click **START** when ready.

### Direct run — skip the wizard

```bash
dfire run \
  --image  data/images/camera_view.jpg \
  --dem    data/dem/srtm-37-04.tif \
  --lat    36.731627 \
  --lon    2.994820 \
  --elev   14 \
  --tilt   -2 \
  --focal  1600 \
  --range  6000
```

### Use the larger AI model

```bash
dfire --large-ai                    # wizard mode
dfire run --large-ai --image ...    # direct mode
```

Downloads Depth-Anything-V2-Base (~400 MB). More accurate on complex terrain and dense vegetation.

### Show current configuration

```bash
dfire info
```

### Keyboard controls (measurement window)

| Key | Action |
|-----|--------|
| Left-click | Measure distance to clicked point |
| `D` | Toggle AI depth map colour overlay |
| `R` | Reset measurement and clear AI anchors |
| `S` | Save annotated result image to `output/` |
| `Q` / `Escape` | Quit |

The **Live Settings** window has five sliders that recalculate the measurement in real time:
camera elevation, tilt, focal length, max range, and pan bearing.

---

## Project structure

```
dfire-estimator/
│
├── dfire/                         # Installable Python package
│   ├── cli.py                     # CLI entry point (the dfire command)
│   │
│   ├── core/                      # Pure algorithms — no UI dependencies
│   │   ├── dem.py                 # DEM loader and GPS elevation lookup
│   │   ├── raycast.py             # Geometric ray casting engine
│   │   └── depth.py               # Depth Anything V2 wrapper
│   │
│   ├── ui/                        # OpenCV windows
│   │   ├── wizard.py              # Setup form window
│   │   └── measure.py             # Measurement window and live sliders
│   │
│   └── utils/                     # Shared helpers
│       ├── config.py              # Typed Config dataclass and .env loading
│       ├── logger.py              # Coloured console logging
│       └── drawing.py             # Resolution-aware OpenCV drawing helpers
│
├── tests/                         # Pytest test suite — 31 tests
│   ├── test_raycast.py
│   ├── test_dem.py
│   └── test_config.py
│
├── scripts/
│   ├── setup_env.sh               # Linux / macOS setup
│   └── setup_env.bat              # Windows setup
│
├── data/
│   ├── dem/                       # Place your DEM file here
│   └── images/                    # Place your camera images here
│
├── models/                        # AI model weights — populated automatically
├── output/                        # Saved annotated result images
├── .env.example                   # Configuration template
├── pyproject.toml                 # Package definition and dependencies
└── README.md
```

---

## Running tests

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pytest                             # all 31 tests
pytest -v                          # verbose output
pytest tests/test_dem.py           # single file
pytest --cov=dfire                 # with coverage report
```

Tests do not require a real DEM file, a camera, or the AI model. They generate synthetic data in temporary directories to test algorithms in isolation.

---

## Camera calibration

An accurate focal length is the most important parameter for distance accuracy.

**Step 1 — Generate a printable chessboard**

```python
import cv2, numpy as np
board = np.kron([[1,0]*5,[0,1]*5]*5, np.ones((60,60))) * 255
cv2.imwrite('chessboard.png', board.astype('uint8'))
```

Print `chessboard.png` on A4 paper. Measure one square with a ruler.

**Step 2 — Take calibration photos**

Take 15–20 photos of the printed board with your camera. Vary the angle and distance in each shot. Ensure the board fills most of the frame and is well-lit with no blur.

**Step 3 — Run calibration**

```bash
dfire calibrate \
  --photos calib_photos/ \
  --square 30              # your measured square size in mm
```

**Step 4 — Update your configuration**

```ini
# .env
DFIRE_FOCAL_LENGTH_PX=1623    # printed by the calibrate command
```

A reprojection error below 0.5 px is excellent. Above 1.0 px — retake the photos with better lighting.

---

## DEM data

A DEM (Digital Elevation Model) file provides the real terrain elevation the ray caster needs to locate ground surfaces accurately. SRTM data is free and covers the entire world at 30-metre resolution.

### Download — Copernicus DEM (recommended)

1. Go to [dem.copernicus.eu](https://dem.copernicus.eu)
2. Search for your area
3. Download the GeoTIFF tile (`.tif` file)

### Download — NASA SRTM via USGS EarthExplorer

1. Go to [earthexplorer.usgs.gov](https://earthexplorer.usgs.gov) (free account required)
2. Draw a bounding box around your camera's field of view
3. Under **Data Sets** select: Digital Elevation → SRTM 1 Arc-Second Global
4. Download the `.hgt` file

### For Algeria and northern Africa

Download tile **srtm_37_04.tif** — covers latitude 35–40°N, longitude 0–5°E, which includes all of northern Algeria.

### File placement

```
data/
└── dem/
    └── srtm-37-04.tif
```

Update `.env`:

```ini
DFIRE_DEM_PATH=data/dem/srtm-37-04.tif
```

Both `.tif` and `.hgt` formats are supported natively.

---

## Accuracy

| Source of error | Typical impact | How to reduce it |
|----------------|---------------|-----------------|
| DEM resolution (30 m grid) | ±15–30 m | Use higher-resolution DEM if available for your area |
| Camera tilt measurement | ±5–20 m per degree of error | Use a precision inclinometer rather than a phone |
| Focal length error | ±5–15 m per 50 px error | Run `dfire calibrate` with good chessboard photos |
| GPS position error | ±5–10 m | Use Google Earth coordinates, not phone GPS |
| AI (uncalibrated, no anchors) | Relative only | Click several DEM-active points first |
| AI (5+ anchors) | ±5–15 m | Click diverse points spread across the scene |

### Best practice for a measurement session

1. Click 5 ground-level points at known features (roads, building edges, clearings) to anchor the AI.
2. Wait for the AI confidence bar to fill to at least 50%.
3. Click the point of interest — both DEM and AI results are now reliable.
4. If both values agree within 10%, the measurement is trustworthy.

---

## Troubleshooting

**`dfire` command not found after setup**

The virtual environment is not active:
```bash
source .venv/bin/activate     # Linux / macOS
.venv\Scripts\activate        # Windows
```

**`Cannot import 'setuptools.backends.legacy'` during installation**

Your pip or setuptools is outdated:
```bash
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

**AI model is very slow**

The model runs on CPU by default and takes 10–30 seconds per image on a typical machine. This is normal. If you have an NVIDIA GPU with CUDA installed it will be detected and used automatically, reducing inference to 1–3 seconds.

**DEM file not found**

Verify the path in `.env` exactly matches the actual filename including the extension. The path is relative to the project root folder. Run `dfire info` to see the path the app is trying to open.

**Distances look completely wrong**

Check these in order:

1. Is `CAMERA_ELEV_M` the elevation above sea level — not just the floor height? It should be the Google Earth elevation at the camera site plus the height of the pole or floor.
2. Is `CAMERA_TILT_DEG` negative? Looking down = negative value. Typical surveillance cameras are between -8 and -20.
3. Is `FOCAL_LENGTH_PX` approximately correct? For a typical phone camera at full resolution it is 1200–2000 px.
4. Does the DEM tile actually cover the area visible in your image?

**Measurement window opens but image appears small**

The window fits to 1600×920 by default. Drag the window corner to any size — the image redraws at full native resolution.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

- [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2) — Lihe Yang et al.
- [SRTM terrain data](https://www2.jpl.nasa.gov/srtm/) — NASA / USGS
- [Copernicus DEM](https://dem.copernicus.eu) — European Space Agency
- [DFire dataset](https://github.com/gaiasd/DFireDataset) — wildfire surveillance imagery
- [OpenCV](https://opencv.org), [rasterio](https://rasterio.readthedocs.io), [PyTorch](https://pytorch.org), [Click](https://click.palletsprojects.com)
