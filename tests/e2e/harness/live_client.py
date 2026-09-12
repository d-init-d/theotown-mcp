"""
Live detector and ground-truth telemetry reader for running TheoTown instance.
"""

from __future__ import annotations

import subprocess
from typing import Any

from theotown_mcp.config import TheoTownConfig, get_config


class LiveDetector:
    """Detects live TheoTown game process and storage artifacts on host."""

    @staticmethod
    def is_game_running() -> bool:
        """Checks whether TheoTown.exe process is currently active on Windows."""
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq TheoTown.exe", "/NH"],
                text=True,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            return "TheoTown.exe" in output
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def probe_local_storage(config: TheoTownConfig | None = None) -> dict[str, Any]:
        """Probes the live local TheoTown storage directory and returns inspection dict."""
        cfg = config or get_config()
        pmodext_exists = cfg.pmodext_path.exists()
        prefs_exists = cfg.prefs_dir.exists()
        pref_count = len(list(cfg.prefs_dir.glob("*"))) if prefs_exists else 0

        pmodext_size = cfg.pmodext_path.stat().st_size if pmodext_exists else 0
        has_hash = False
        if pmodext_exists:
            raw = cfg.pmodext_path.read_text(encoding="utf-8", errors="replace")
            has_hash = "#" in raw

        return {
            "installed": cfg.is_installed(),
            "pmodext_exists": pmodext_exists,
            "pmodext_size": pmodext_size,
            "has_hash_delimiter": has_hash,
            "prefs_exists": prefs_exists,
            "prefs_count": pref_count,
            "game_running": LiveDetector.is_game_running(),
        }
