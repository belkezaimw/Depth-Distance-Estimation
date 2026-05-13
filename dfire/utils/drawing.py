"""
dfire.utils.drawing
===================
High-quality, resolution-aware drawing helpers for the measurement window.

Uses PIL/Pillow for text rendering (TrueType fonts, antialiased) instead of
OpenCV's Hershey bitmap fonts. Result is dramatically sharper text at all
image sizes.

All element sizes scale with image width so the overlay looks proportional
whether the image is 416px or 4000px wide.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ─────────────────────────────────────────────────────────────────────────────
# Palette (BGR for OpenCV drawing, RGB for PIL)
# ─────────────────────────────────────────────────────────────────────────────
class Palette:
    # BGR (OpenCV)
    BG     = (18,  20,  26)
    PANEL  = (28,  32,  42)
    BORDER = (55,  62,  78)
    ACCENT = (36, 180, 255)
    ORANGE = (30, 150, 240)
    GREEN  = (55, 210,  90)
    RED    = (55,  55, 220)
    PURPLE = (200, 75, 175)
    WHITE  = (240, 240, 245)
    GRAY   = (120, 128, 145)
    DARK   = (12,  14,  18)
    YELLOW = (30, 215, 255)

    # RGB equivalents for PIL
    @staticmethod
    def to_rgb(bgr):
        return (bgr[2], bgr[1], bgr[0])

P = Palette()

# Keep OpenCV font as fallback only
FONT  = cv2.FONT_HERSHEY_SIMPLEX
FONTB = cv2.FONT_HERSHEY_DUPLEX


# ─────────────────────────────────────────────────────────────────────────────
# Font loader — finds best available TrueType font
# ─────────────────────────────────────────────────────────────────────────────
_FONT_SEARCH = [
    # Windows
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/arial.ttf",
    # Linux (DejaVu — always present on Ubuntu)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    # Fallback extras
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
]

_FONT_SEARCH_BOLD = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
]


def _find_font(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


_FONT_PATH      = _find_font(_FONT_SEARCH)
_FONT_PATH_BOLD = _find_font(_FONT_SEARCH_BOLD) or _FONT_PATH

_font_cache: dict[tuple, ImageFont.FreeTypeFont] = {}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _font_cache:
        path = _FONT_PATH_BOLD if bold else _FONT_PATH
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


# ─────────────────────────────────────────────────────────────────────────────
# Core: draw PIL text onto a BGR OpenCV image
# ─────────────────────────────────────────────────────────────────────────────

def _put_text(
    img: np.ndarray,
    text: str,
    x: int, y: int,
    color_bgr: tuple,
    size: int = 14,
    bold: bool = False,
    anchor: str = "lt",   # "lt"=left-top  "mt"=centre-top  "rt"=right-top
) -> None:
    """
    Draw antialiased TrueType text onto a BGR OpenCV image using PIL.
    x, y = top-left corner of the text bounding box (anchor='lt')
             or centre-x / top-y (anchor='mt')
    """
    H, W = img.shape[:2]
    font   = _get_font(size, bold)
    color  = P.to_rgb(color_bgr)

    # Get text bounding box to validate placement
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox  = dummy.textbbox((0, 0), text, font=font, anchor="lt")
    tw    = bbox[2] - bbox[0]
    th    = bbox[3] - bbox[1]

    # Adjust for anchor
    if anchor == "mt":
        x = x - tw // 2
    elif anchor == "rt":
        x = x - tw

    # Clamp to image bounds
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))

    # Create small RGBA patch, draw text, composite onto img
    pw = min(tw + 4, W - x)
    ph = min(th + 4, H - y)
    if pw <= 0 or ph <= 0:
        return

    patch = Image.fromarray(
        cv2.cvtColor(img[y:y+ph, x:x+pw], cv2.COLOR_BGR2RGB)
    ).convert("RGBA")
    txt_layer = Image.new("RGBA", patch.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    draw.text((0, 2), text, font=font, fill=(*color, 255), anchor="lt")
    composited = Image.alpha_composite(patch, txt_layer).convert("RGB")
    img[y:y+ph, x:x+pw] = cv2.cvtColor(np.array(composited), cv2.COLOR_RGB2BGR)


def _text_width(text: str, size: int, bold: bool = False) -> int:
    font  = _get_font(size, bold)
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox  = dummy.textbbox((0, 0), text, font=font, anchor="lt")
    return bbox[2] - bbox[0]


# ─────────────────────────────────────────────────────────────────────────────
# DrawHelper
# ─────────────────────────────────────────────────────────────────────────────

class DrawHelper:
    """
    High-quality drawing helper. All sizes scale with image width.
    Uses PIL for text (antialiased TrueType) and OpenCV for shapes.
    """

    def __init__(self, img_width: int) -> None:
        # sc=1 at 900px wide, scales linearly
        self.sc   = max(1.0, img_width / 900.0)
        self.iw   = img_width
        # Base font sizes (at sc=1)
        self.fs_sm  = max(11, int(12 * self.sc))  # small labels
        self.fs_md  = max(13, int(14 * self.sc))  # regular text
        self.fs_lg  = max(18, int(22 * self.sc))  # big distance number
        self.fs_xl  = max(26, int(34 * self.sc))  # headline distance

    # ── text ──────────────────────────────────────────────────────────────────

    def text(
        self, img, s: str, x: int, y: int,
        color=P.WHITE, size: int = 0, bold: bool = False,
        anchor: str = "lt",
    ) -> None:
        sz = int(size) if (size and int(size) >= 8) else self.fs_md
        _put_text(img, str(s), x, y, color, sz, bool(bold), anchor)

    # ── semi-transparent rectangle ────────────────────────────────────────────

    @staticmethod
    def semi_rect(
        img, x0: int, y0: int, x1: int, y1: int,
        color=P.DARK, alpha: float = 0.82,
    ) -> None:
        H, W = img.shape[:2]
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(W, x1); y1 = min(H, y1)
        if x1 <= x0 or y1 <= y0:
            return
        roi = img[y0:y1, x0:x1]
        cv2.addWeighted(
            np.full_like(roi, color), alpha,
            roi, 1 - alpha, 0, roi,
        )

    # ── badge / pill label ────────────────────────────────────────────────────

    def badge(
        self, img, s: str, x: int, y: int,
        bg=P.ACCENT, fg=P.DARK, size: int = 0,
    ) -> None:
        """Pill-shaped label with coloured background."""
        sz  = int(size) if (size and int(size) >= 8) else self.fs_md
        tw  = _text_width(s, sz)
        pad = max(6, int(8 * self.sc))
        H, W = img.shape[:2]

        bx0 = max(2, min(int(x), W - tw - pad*2 - 2))
        bx1 = bx0 + tw + pad * 2
        by0 = max(2, int(y))
        by1 = by0 + sz + pad + 4
        by1 = min(H - 2, by1)

        radius = max(4, int(6 * self.sc))
        # Rounded rectangle via convex hull trick
        cv2.rectangle(img, (bx0+radius, by0), (bx1-radius, by1), bg, -1)
        cv2.rectangle(img, (bx0, by0+radius), (bx1, by1-radius), bg, -1)
        for cx2, cy2 in [(bx0+radius, by0+radius), (bx1-radius, by0+radius),
                         (bx0+radius, by1-radius), (bx1-radius, by1-radius)]:
            cv2.circle(img, (cx2, cy2), radius, bg, -1)

        _put_text(img, s, bx0+pad, by0+2, fg, sz, bold=True)

    # ── crosshair ─────────────────────────────────────────────────────────────

    def crosshair(
        self, img, cx: int, cy: int,
        color=P.ORANGE, r: int = 14, thick: int = 2,
    ) -> None:
        r  = max(8,  int(r    * self.sc))
        th = max(1,  int(thick* self.sc))
        dot= max(2,  int(3    * self.sc))
        g  = r + int(5  * self.sc)
        e  = r + int(20 * self.sc)

        cv2.circle(img, (cx, cy), r,   color, th,  cv2.LINE_AA)
        cv2.circle(img, (cx, cy), dot, color, -1,  cv2.LINE_AA)
        for a, b in [
            ((cx-e, cy), (cx-g, cy)), ((cx+g, cy), (cx+e, cy)),
            ((cx, cy-e), (cx, cy-g)), ((cx, cy+g), (cx, cy+e)),
        ]:
            cv2.line(img, a, b, color, max(1, th-1), cv2.LINE_AA)

    # ── info panel ────────────────────────────────────────────────────────────

    def info_panel(
        self,
        img,
        dist_str:   str,
        rows:       list[tuple[str, str, tuple]],
        confidence: float = 0.0,
        at_max:     bool  = False,
        max_range:  int   = 0,
    ) -> None:
        sc  = self.sc
        p   = max(10, int(14 * sc))     # padding
        pw  = max(250, int(290 * sc))   # panel width
        rh  = max(16, int(18 * sc))     # row height

        # Panel height: title + big dist + rows + confidence bar
        ph = (p                         # top pad
              + self.fs_sm + 6          # "DISTANCE FROM CAMERA" label
              + self.fs_xl + 12         # big distance number
              + len(rows) * rh          # detail rows
              + (rh + 10 if confidence > 0 else 0)  # confidence bar
              + p)                      # bottom pad

        H, W = img.shape[:2]
        x0, y0 = p, p
        x1 = min(x0 + pw, W - 2)
        y1 = min(y0 + ph, H - 2)

        # Background
        self.semi_rect(img, x0, y0, x1, y1, P.DARK, 0.88)

        # Border
        cv2.rectangle(img, (x0, y0), (x1, y1), P.BORDER, 1, cv2.LINE_AA)

        # Accent left bar
        bar_w = max(3, int(4 * sc))
        cv2.rectangle(img, (x0, y0), (x0+bar_w, y1), P.ACCENT, -1)

        # "DISTANCE FROM CAMERA" label
        ty = y0 + p
        _put_text(img, "DISTANCE FROM CAMERA",
                  x0+bar_w+p, ty, P.GRAY, self.fs_sm)
        ty += self.fs_sm + 6

        # Big distance number
        _put_text(img, dist_str,
                  x0+bar_w+p, ty, P.ORANGE, self.fs_xl, bold=True)
        ty += self.fs_xl + 14

        # Separator line
        cv2.line(img,
                 (x0+bar_w+p, ty - 6),
                 (x1 - p, ty - 6),
                 P.BORDER, 1)

        # Detail rows
        lbl_x = x0 + bar_w + p
        val_x = x0 + bar_w + p + max(95, int(110 * sc))

        for lbl, val, col in rows:
            _put_text(img, lbl + ":", lbl_x, ty, P.GRAY, self.fs_sm)
            _put_text(img, val,       val_x, ty, col,    self.fs_sm)
            ty += rh

        # Confidence bar
        if confidence > 0:
            bar_y  = ty + 6
            bar_h  = max(5, int(7 * sc))
            bar_w2 = x1 - p - lbl_x
            _put_text(img, "AI confidence:", lbl_x, bar_y, P.GRAY, self.fs_sm)
            bar_y2 = bar_y + self.fs_sm + 4
            cv2.rectangle(img, (lbl_x, bar_y2),
                          (lbl_x+bar_w2, bar_y2+bar_h), P.BORDER, -1)
            filled = max(1, int(bar_w2 * confidence))
            cv2.rectangle(img, (lbl_x, bar_y2),
                          (lbl_x+filled, bar_y2+bar_h), P.YELLOW, -1)

        if at_max and max_range:
            _put_text(img, f"max range {max_range:,} m",
                      x0+bar_w+p, y1-p, (100, 100, 200), self.fs_sm)

    # ── status bar ────────────────────────────────────────────────────────────

    def status_bar(
        self, img, ai_ready: bool, dem_on: bool, depth_on: bool,
    ) -> None:
        H, W = img.shape[:2]
        bh   = max(22, int(26 * self.sc))
        cv2.rectangle(img, (0, H-bh), (W, H), P.DARK, -1)
        cv2.line(img, (0, H-bh), (W, H-bh), P.BORDER, 1)

        parts = [
            (f"AI: {'ready ✓' if ai_ready else 'loading…'}",
             P.GREEN if ai_ready else P.YELLOW),
            (f"DEM: {'on' if dem_on else 'off'}",
             P.GREEN if dem_on else P.GRAY),
            (f"Depth: {'ON' if depth_on else 'off'} [D]",
             P.ACCENT if depth_on else P.GRAY),
            ("Click=measure  R=reset  S=save  Q=quit", P.GRAY),
        ]
        ty = H - bh + max(4, int(5 * self.sc))
        x  = max(8, int(10 * self.sc))
        for label, col in parts:
            _put_text(img, label, x, ty, col, self.fs_sm)
            x += _text_width(label, self.fs_sm) + max(20, int(28 * self.sc))
            if x > W - 200:
                break