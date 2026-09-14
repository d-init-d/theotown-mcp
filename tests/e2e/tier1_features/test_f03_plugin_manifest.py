"""Tier 1: static plugin manifest and protocol-v2 mailbox tests."""

from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.lua_syntax_check import check_lua_syntax


class TestFeatureF03PluginManifest:
    def test_e2e_t1_f03_01_manifest_schema(self):
        """Validate plugin/theotown_mcp/plugin.json schema and draft array."""
        manifest_path = Path("plugin/theotown_mcp/plugin.json")
        assert manifest_path.exists()

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1

    def test_e2e_t1_f03_02_multi_draft_declarations(self):
        """Verify only the static core engine is executable."""
        manifest_path = Path("plugin/theotown_mcp/plugin.json")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))

        draft_ids = [d.get("id") for d in data]
        assert "$theotown_mcp_core" in draft_ids
        assert "$theotown_mcp_inbox" not in draft_ids

    def test_e2e_t1_f03_03_dev_flag_on_inbox(self):
        """Ensure no runtime-reloaded executable mailbox is declared."""
        manifest_path = Path("plugin/theotown_mcp/plugin.json")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert all(d.get("dev") is not True for d in data)
        assert [d.get("script") for d in data] == ["core.lua"]

    def test_e2e_t1_f03_04_hot_reload_trigger(self, mock_env: MockTheoTownEnv):
        """Validate the static core with TheoTown's Lua parser."""
        clean, msg = check_lua_syntax(Path("plugin/theotown_mcp/core.lua"))
        assert clean, msg

    def test_e2e_t1_f03_05_plugin_directory_structure(self):
        """Verify repository plugin directory layout."""
        base = Path("plugin/theotown_mcp")
        assert (base / "plugin.json").exists()
        assert (base / "core.lua").exists()
        assert (base / "inbox.lua").exists()
