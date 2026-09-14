"""
Asset resolution and installation utilities for TheoTown MCP Server.
Provides safe discovery of in-game Lua plugin files from wheel package data or repository.
"""

from __future__ import annotations

import importlib.resources
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

PLUGIN_FILE_NAMES = ("plugin.json", "core.lua", "inbox.lua")


def get_plugin_assets_dir() -> Path:
    """
    Locates the in-game TheoTown Lua plugin assets directory.

    Searches in order:
    1. Packaged resource inside the Python distribution (`importlib.resources`).
    2. Repository checkout relative to this file (`../../plugin/theotown_mcp`).
    3. Current working directory (`./plugin/theotown_mcp`).

    Returns:
        Path to the directory containing `plugin.json`, `core.lua`, and `inbox.lua`.

    Raises:
        FileNotFoundError: If plugin assets cannot be found in any candidate location.
    """
    # 1. Check packaged resource
    try:
        resource_dir = Path(str(importlib.resources.files("theotown_mcp").joinpath("plugin_assets", "theotown_mcp")))
        if (
            resource_dir.exists()
            and resource_dir.is_dir()
            and all((resource_dir / f).exists() for f in PLUGIN_FILE_NAMES)
        ):
            return resource_dir
    except (TypeError, FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass

    # 2. Check repository source
    repo_dir = Path(__file__).resolve().parent.parent.parent / "plugin" / "theotown_mcp"
    if repo_dir.exists() and repo_dir.is_dir() and all((repo_dir / f).exists() for f in PLUGIN_FILE_NAMES):
        return repo_dir

    # 3. Check current working directory
    cwd_dir = Path.cwd() / "plugin" / "theotown_mcp"
    if cwd_dir.exists() and cwd_dir.is_dir() and all((cwd_dir / f).exists() for f in PLUGIN_FILE_NAMES):
        return cwd_dir

    raise FileNotFoundError(
        "Could not locate TheoTown MCP plugin assets ('plugin.json', 'core.lua', 'inbox.lua'). "
        "Ensure the package was built with plugin assets or run from the repository root."
    )


def install_plugin_files(
    target_dir: Path,
    force: bool = False,
    backup: bool = True,
    symlink: bool = False,
) -> list[Path]:
    """
    Safely installs or upgrades plugin files into the target TheoTown plugin directory.

    Guarantees:
    - Preserves all other files in `target_dir` (e.g. telemetry.txt, job status files).
    - Creates `.bak` backups before overwriting existing files if `backup=True`.
    - Idempotent and safe against partial installs.

    Returns:
        List of paths to newly installed/updated files.
    """
    source_dir = get_plugin_assets_dir()
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    installed_files: list[Path] = []
    for filename in PLUGIN_FILE_NAMES:
        src_file = source_dir / filename
        dst_file = target_dir / filename

        if not src_file.exists():
            continue

        if dst_file.exists():
            if not force:
                logger.warning("Skipping existing plugin file %s (use --force to overwrite)", dst_file)
                continue
            if backup and not dst_file.is_symlink():
                backup_file = dst_file.with_suffix(dst_file.suffix + ".bak")
                try:
                    shutil.copy2(dst_file, backup_file)
                except OSError:
                    pass

        if symlink:
            try:
                if dst_file.exists() or dst_file.is_symlink():
                    dst_file.unlink()
                dst_file.symlink_to(src_file)
                installed_files.append(dst_file)
                continue
            except OSError:
                pass

        shutil.copy2(src_file, dst_file)
        installed_files.append(dst_file)

    return installed_files
