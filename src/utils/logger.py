# apex_scalper/src/utils/logger.py
"""
APEX Scalper — Logging Utility
================================
Windows-safe logger. Uses a plain FileHandler (mode='w') instead of
RotatingFileHandler which throws PermissionError on Windows when it tries
to os.rename() an open log file during rollover.

Log file is overwritten on each new run. Console output always shown.
"""

import logging
import os
from config.settings import LOG_LEVEL, LOG_FILE

_CONFIGURED = False   # Guard against duplicate handler attachment on re-import


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger. Root handlers are configured once on first call.
    All child loggers inherit them automatically.

    Args:
        name: Module name — pass __name__ at call site.
    """
    global _CONFIGURED
    if not _CONFIGURED:
        _setup_root_logger()
        _CONFIGURED = True
    return logging.getLogger(name)


def _setup_root_logger():
    """Attach console + file handlers to the root logger exactly once."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    root.handlers.clear()   # Avoid duplicate handlers on hot-reloads

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console ──────────────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # ── File (plain, mode='w') ────────────────────────────────────────────
    # mode='w' truncates the log at the start of each run.
    # This avoids PermissionError [WinError 32] caused by RotatingFileHandler
    # calling os.rename() on a file still open by the same process on Windows.
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
