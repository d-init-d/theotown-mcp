"""
Configuration and path auto-detection for TheoTown MCP Server.
Resolves Windows %USERPROFILE%\\TheoTown directory and handles THEOTOWN_DATA_DIR override.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class TheoTownConfig(BaseModel):
    """Path configuration for TheoTown installation and IPC channels."""

    data_dir_override: Path | None = Field(default=None, description="Explicit directory override")

    @property
    def theotown_data_dir(self) -> Path:
        """Resolves active TheoTown data directory."""
        if self.data_dir_override is not None:
            return Path(self.data_dir_override)

        env_dir = os.environ.get("THEOTOWN_DATA_DIR")
        if env_dir:
            return Path(env_dir)

        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            return Path(user_profile) / "TheoTown"

        return Path.home() / "TheoTown"

    @property
    def plugins_root(self) -> Path:
        """Root plugins directory inside TheoTown data folder."""
        return self.theotown_data_dir / "plugins"

    @property
    def plugin_dir(self) -> Path:
        """Target directory for theotown_mcp plugin."""
        return self.plugins_root / "theotown_mcp"

    @property
    def inbox_path(self) -> Path:
        """Legacy static Lua file retained for compatibility checks."""
        return self.plugin_dir / "inbox.lua"

    @property
    def requests_path(self) -> Path:
        """Durable JSON command mailbox consumed by core.lua."""
        return self.plugin_dir / "requests.txt"

    @property
    def mailbox_lock_path(self) -> Path:
        """Cross-process lock protecting requests.txt read-modify-write operations."""
        return self.plugin_dir / "requests.lock"

    @property
    def telemetry_path(self) -> Path:
        """Telemetry state file written by Lua core.lua."""
        return self.plugin_dir / "telemetry.txt"

    @property
    def drafts_path(self) -> Path:
        """Cached drafts catalog file exported by core.lua."""
        return self.plugin_dir / "drafts.txt"

    @property
    def pmodext_path(self) -> Path:
        """Pmodext persistent storage file in TheoTown root."""
        return self.theotown_data_dir / ".pmodext"

    @property
    def prefs_dir(self) -> Path:
        """SharedPreferences directory for TheoTown."""
        user_profile = os.environ.get("USERPROFILE")
        base = Path(user_profile) if user_profile else Path.home()
        return base / ".prefs" / "theotown"

    def is_installed(self) -> bool:
        """Checks if the configured TheoTown data directory exists."""
        return self.theotown_data_dir.exists() and self.theotown_data_dir.is_dir()

    def ensure_directories(self) -> None:
        """Ensures that the plugin directory exists."""
        self.plugin_dir.mkdir(parents=True, exist_ok=True)


_global_config: TheoTownConfig | None = None


def get_config(data_dir_override: Path | str | None = None, refresh: bool = False) -> TheoTownConfig:
    """Retrieves or initializes the TheoTownConfig instance."""
    global _global_config
    if data_dir_override is not None:
        return TheoTownConfig(data_dir_override=Path(data_dir_override))
    if _global_config is None or refresh:
        _global_config = TheoTownConfig()
    return _global_config


def reset_config() -> None:
    """Resets the global config singleton for clean test isolation."""
    global _global_config
    _global_config = None
