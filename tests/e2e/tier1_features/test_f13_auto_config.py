"""
Tier 1: Feature F13 — Auto-Configuration
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from theotown_mcp.config import TheoTownConfig


class TestFeatureF13AutoConfig:
    def test_e2e_t1_f13_01_userprofile_detection(self):
        """Auto-detection of USERPROFILE\\TheoTown on Windows."""
        fake_profile = "C:\\Users\\MockUser"
        with patch.dict("os.environ", {"USERPROFILE": fake_profile}, clear=True):
            cfg = TheoTownConfig()
            assert cfg.theotown_data_dir == Path(fake_profile) / "TheoTown"

    def test_e2e_t1_f13_02_env_override(self):
        """THEOTOWN_DATA_DIR environment variable override."""
        custom_dir = "D:\\Games\\TheoTownData"
        with patch.dict("os.environ", {"THEOTOWN_DATA_DIR": custom_dir}):
            cfg = TheoTownConfig()
            assert cfg.theotown_data_dir == Path(custom_dir)

    def test_e2e_t1_f13_03_plugin_dir_resolution(self):
        """Resolution of plugin_dir under plugins/theotown_mcp."""
        base = Path("C:/MockTown")
        cfg = TheoTownConfig(data_dir_override=base)
        assert cfg.plugin_dir == base / "plugins" / "theotown_mcp"

    def test_e2e_t1_f13_04_inbox_path_resolution(self):
        """Resolution of inbox.lua path inside plugin directory."""
        base = Path("C:/MockTown")
        cfg = TheoTownConfig(data_dir_override=base)
        assert cfg.inbox_path == base / "plugins" / "theotown_mcp" / "inbox.lua"

    def test_e2e_t1_f13_05_missing_directory_detection(self, tmp_path: Path):
        """Detection of non-existent directory via is_installed()."""
        cfg = TheoTownConfig(data_dir_override=tmp_path / "NonExistent")
        assert cfg.is_installed() is False
