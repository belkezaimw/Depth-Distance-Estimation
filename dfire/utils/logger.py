"""
dfire.utils.logger
==================
Centralised logging setup using Python's standard logging module.
Outputs coloured, timestamped messages to the console.
"""

from __future__ import annotations
import logging
import sys


_COLOURS = {
    "DEBUG":    "\033[36m",    # cyan
    "INFO":     "\033[32m",    # green
    "WARNING":  "\033[33m",    # yellow
    "ERROR":    "\033[31m",    # red
    "CRITICAL": "\033[35m",    # magenta
}
_RESET = "\033[0m"


class _ColourFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        colour = _COLOURS.get(record.levelname, "")
        record.levelname = f"{colour}{record.levelname:8s}{_RESET}"
        return super().format(record)


def setup_logging(level: str = "INFO") -> None:
    """
    Configure root logger with coloured console output.
    Call once at application startup.

    Parameters
    ----------
    level : "DEBUG" | "INFO" | "WARNING" | "ERROR"
    """
    numeric = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _ColourFormatter(
            fmt  = "%(asctime)s  %(levelname)s  %(name)s — %(message)s",
            datefmt = "%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric)

    # Silence noisy third-party loggers
    for noisy in ("transformers", "torch", "PIL", "rasterio", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
