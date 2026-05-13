"""
dfire.ui.wizard
===============
Native OS setup wizard built with tkinter.

Why tkinter instead of OpenCV:
  - Real text entry fields — you can type, paste, select, backspace normally
  - Native OS file picker (Browse button)
  - Proper fonts, DPI-aware rendering
  - Works on Windows, macOS, and Linux without extra dependencies
"""

from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2

from dfire.core.dem     import DEM
from dfire.utils.config import Config

log = logging.getLogger(__name__)

# ── field definitions ─────────────────────────────────────────────────────────
_FIELDS = [
    # (label, config_key, default_value, hint_text, is_file)
    ("Camera latitude  (°N)",          "camera_lat",        "36.731627", "e.g. 36.7516 — from Google Maps",         False),
    ("Camera longitude (°E)",          "camera_lon",        "2.994820",  "e.g. 2.9942 — from Google Maps",          False),
    ("Camera elevation (m ASL)",       "camera_abs_elev_m", "14",        "ground elevation + floor height in metres",False),
    ("Camera tilt (° negative=down)",  "camera_tilt_deg",   "-2",        "measure with phone inclinometer app",      False),
    ("Focal length (px)",              "focal_length_px",   "1600",      "from calibrate.py or camera spec sheet",   False),
    ("Pan / compass bearing (°)",      "camera_pan_deg",    "0",         "0=North  90=East  180=South  270=West",    False),
    ("Max search range (m)",           "max_range_m",       "6000",      "6000 for hills, 500 for urban scenes",     False),
    ("Valley / ground floor (m ASL)",  "valley_floor_m",    "0",         "lowest terrain elevation in the scene",    False),
    ("DEM file (.tif or .hgt)",        "dem_path",          "",          "optional — leave blank for flat ground",   True),
    ("Image file",                     "image_path",        "",          "your camera photo (JPG, PNG, etc.)",       True),
]


class SetupWizard:
    """
    Tkinter-based setup form.

    Usage
    -----
    >>> wizard = SetupWizard(default_cfg)
    >>> result = wizard.run()   # blocks until user clicks START
    >>> cfg, dem, image = result["cfg"], result["dem"], result["image"]
    """

    def __init__(self, default_cfg: Config) -> None:
        self._result = None
        self._cfg    = default_cfg
        self._root   = None

    # ── public ────────────────────────────────────────────────────────────────

    def run(self) -> dict:
        """Show the form and block until the user clicks START. Returns result dict."""
        self._root = tk.Tk()
        self._build_ui(self._root)
        self._root.mainloop()

        if self._result is None:
            # User closed the window
            sys.exit(0)
        return self._result

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, root: tk.Tk) -> None:
        root.title("DFire Distance Estimator — Setup")
        root.resizable(True, True)

        # ── colours ──────────────────────────────────────────────────────────
        BG        = "#13151c"   # dark background
        PANEL     = "#1c1f2b"   # card background
        BORDER    = "#2e3347"   # subtle border
        ACCENT    = "#1eb8ff"   # cyan accent
        LABEL_FG  = "#7a8099"   # muted label
        INPUT_BG  = "#252839"   # entry background
        INPUT_FG  = "#e8eaf0"   # entry text
        HINT_FG   = "#454d6a"   # placeholder hint
        BTN_START = "#1eb8ff"   # start button
        BTN_FG    = "#0a0d15"   # start button text
        BROWSE_BG = "#252839"
        BROWSE_FG = ACCENT
        ERROR_FG  = "#ff5a5a"

        root.configure(bg=BG)

        # ── ttk style (for the scrollbar) ─────────────────────────────────────
        style = ttk.Style(root)
        style.theme_use("default")
        style.configure("Vertical.TScrollbar",
                         background=PANEL, troughcolor=BG,
                         arrowcolor=LABEL_FG, borderwidth=0)

        # ── outer frame with padding ──────────────────────────────────────────
        outer = tk.Frame(root, bg=BG)
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        # ── header ───────────────────────────────────────────────────────────
        header = tk.Frame(outer, bg=PANEL, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)

        accent_bar = tk.Frame(header, bg=ACCENT, width=5)
        accent_bar.pack(side="left", fill="y")

        htext = tk.Frame(header, bg=PANEL)
        htext.pack(side="left", fill="both", expand=True, padx=20, pady=12)

        tk.Label(htext, text="DFIRE DISTANCE ESTIMATOR",
                 font=("Segoe UI", 14, "bold"),
                 fg=ACCENT, bg=PANEL).pack(anchor="w")
        tk.Label(htext, text="AI + DEM Edition  —  Camera Setup",
                 font=("Segoe UI", 9),
                 fg=LABEL_FG, bg=PANEL).pack(anchor="w")

        # ── scrollable content area ───────────────────────────────────────────
        canvas_frame = tk.Frame(outer, bg=BG)
        canvas_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(canvas_frame, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical",
                                   command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        content = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=content,
                                              anchor="nw", tags="content")

        def _on_resize(e):
            canvas.itemconfig("content", width=e.width)
        canvas.bind("<Configure>", _on_resize)

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        content.bind("<Configure>", _on_frame_configure)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── field grid ────────────────────────────────────────────────────────
        fields_frame = tk.Frame(content, bg=BG)
        fields_frame.pack(fill="x", padx=24, pady=20)

        self._entries: dict[str, tk.StringVar] = {}

        for i, (label, key, default, hint, is_file) in enumerate(_FIELDS):
            row = i // 2
            col = i % 2

            # Pre-fill from config
            cfg_val = getattr(self._cfg, key, None)
            init_val = str(cfg_val) if cfg_val else default

            # Card container
            card = tk.Frame(fields_frame, bg=PANEL,
                            highlightbackground=BORDER,
                            highlightthickness=1)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            fields_frame.columnconfigure(col, weight=1)

            inner = tk.Frame(card, bg=PANEL)
            inner.pack(fill="both", padx=14, pady=12)

            # Label
            tk.Label(inner, text=label,
                     font=("Segoe UI", 8),
                     fg=LABEL_FG, bg=PANEL).pack(anchor="w", pady=(0, 4))

            # Entry row
            entry_row = tk.Frame(inner, bg=PANEL)
            entry_row.pack(fill="x")

            var = tk.StringVar(value=init_val)
            self._entries[key] = var

            entry = tk.Entry(entry_row,
                             textvariable=var,
                             font=("Segoe UI", 10),
                             fg=INPUT_FG, bg=INPUT_BG,
                             insertbackground=ACCENT,
                             relief="flat",
                             bd=0,
                             highlightthickness=1,
                             highlightcolor=ACCENT,
                             highlightbackground=BORDER)

            if is_file:
                entry.pack(side="left", fill="x", expand=True,
                           ipady=7, padx=(0, 6))
                browse_key = key  # capture for closure
                btn = tk.Button(entry_row,
                                text="Browse",
                                font=("Segoe UI", 8),
                                fg=BROWSE_FG, bg=BROWSE_BG,
                                activeforeground=ACCENT,
                                activebackground=BORDER,
                                relief="flat", bd=0,
                                padx=10, pady=7,
                                cursor="hand2",
                                highlightthickness=1,
                                highlightbackground=BORDER,
                                command=lambda k=browse_key: self._browse(k))
                btn.pack(side="right")
            else:
                entry.pack(fill="x", ipady=7)

            # Hint text
            tk.Label(inner, text=hint,
                     font=("Segoe UI", 7),
                     fg=HINT_FG, bg=PANEL).pack(anchor="w", pady=(4, 0))

        # ── error label ───────────────────────────────────────────────────────
        self._error_var = tk.StringVar()
        self._error_lbl = tk.Label(content,
                                    textvariable=self._error_var,
                                    font=("Segoe UI", 9),
                                    fg=ERROR_FG, bg=BG,
                                    wraplength=700,
                                    justify="left")
        self._error_lbl.pack(padx=32, pady=(0, 8), anchor="w")

        # ── bottom bar ────────────────────────────────────────────────────────
        bottom = tk.Frame(outer, bg=PANEL, height=64)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        tk.Label(bottom,
                 text="Tip: you can paste coordinates directly into the fields",
                 font=("Segoe UI", 8), fg=LABEL_FG, bg=PANEL).pack(
                 side="left", padx=20)

        start_btn = tk.Button(bottom,
                              text="  START  ▶  ",
                              font=("Segoe UI", 11, "bold"),
                              fg=BTN_FG, bg=BTN_START,
                              activeforeground=BTN_FG,
                              activebackground="#17a0df",
                              relief="flat", bd=0,
                              padx=24, pady=14,
                              cursor="hand2",
                              command=self._commit)
        start_btn.pack(side="right", padx=20, pady=10)

        # Keyboard shortcut
        root.bind("<Return>", lambda e: self._commit())
        root.bind("<Escape>", lambda e: sys.exit(0))

        # ── size and centre the window ────────────────────────────────────────
        root.update_idletasks()
        w, h = 860, 720
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.minsize(680, 500)

    # ── browse ────────────────────────────────────────────────────────────────

    def _browse(self, key: str) -> None:
        if key == "dem_path":
            path = filedialog.askopenfilename(
                title="Select DEM file",
                filetypes=[
                    ("DEM files", "*.tif *.tiff *.hgt *.img"),
                    ("All files", "*.*"),
                ],
            )
        else:
            path = filedialog.askopenfilename(
                title="Select camera image",
                filetypes=[
                    ("Images", "*.jpg *.jpeg *.png *.bmp *.tiff"),
                    ("All files", "*.*"),
                ],
            )
        if path:
            self._entries[key].set(path)

    # ── validation & commit ───────────────────────────────────────────────────

    def _commit(self) -> None:
        self._error_var.set("")

        # Parse numeric fields
        numeric: dict = {}
        num_keys = [f[1] for f in _FIELDS if not f[4]]
        for key in num_keys:
            raw = self._entries[key].get().strip()
            try:
                numeric[key] = float(raw)
            except ValueError:
                self._error_var.set(
                    f"'{key}' must be a number — got: {raw!r}")
                return

        if numeric.get("focal_length_px", 0) < 10:
            self._error_var.set("Focal length must be > 10 px")
            return

        # Image
        img_path = self._entries["image_path"].get().strip()
        if not img_path or not os.path.exists(img_path):
            self._error_var.set(
                "Image file not found — click Browse to select it")
            return
        image = cv2.imread(img_path)
        if image is None:
            self._error_var.set(
                "Cannot open image (unsupported format or corrupted file)")
            return

        # DEM (optional)
        dem = None
        dem_path = self._entries["dem_path"].get().strip()
        if dem_path:
            if not os.path.exists(dem_path):
                self._error_var.set(
                    "DEM file not found — click Browse or leave blank")
                return
            try:
                dem = DEM(dem_path)
            except Exception as exc:
                self._error_var.set(f"DEM error: {exc}")
                return

        cfg = Config(**numeric)
        cfg.image_width_px  = image.shape[1]
        cfg.image_height_px = image.shape[0]
        cfg.dem_path        = dem_path

        log.info("Setup complete — image %dx%d  DEM: %s",
                 image.shape[1], image.shape[0],
                 os.path.basename(dem_path) if dem_path else "none")

        self._result = {
            "cfg":        cfg,
            "dem":        dem,
            "image":      image,
            "image_path": img_path,
        }

        self._root.destroy()