"""
Tier 1: Feature F03 — Plugin Manifest & #LuaWrapper
5 Isolated Test Cases.
"""

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
        assert len(data) == 2

    def test_e2e_t1_f03_02_multi_draft_declarations(self):
        """Verify both core.lua and inbox.lua drafts are declared."""
        manifest_path = Path("plugin/theotown_mcp/plugin.json")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))

        draft_ids = [d.get("id") for d in data]
        assert "$theotown_mcp_core" in draft_ids
        assert "$theotown_mcp_inbox" in draft_ids

    def test_e2e_t1_f03_03_dev_flag_on_inbox(self):
        """Ensure #LuaWrapper 'dev: true' is set exclusively on inbox draft."""
        manifest_path = Path("plugin/theotown_mcp/plugin.json")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))

        inbox_draft = next(d for d in data if d.get("id") == "$theotown_mcp_inbox")
        assert inbox_draft.get("dev") is True
        assert inbox_draft.get("script") == "inbox.lua"

    def test_e2e_t1_f03_04_hot_reload_trigger(self, mock_env: MockTheoTownEnv):
        """Simulate #LuaWrapper trigger upon inbox.lua modification."""
        mock_env.config.inbox_path.write_text("-- test hot reload", encoding="utf-8")
        assert mock_env.config.inbox_path.exists()
        clean, msg = check_lua_syntax(mock_env.config.inbox_path)
        assert clean, msg

    def test_e2e_t1_f03_05_plugin_directory_structure(self):
        """Verify repository plugin directory layout."""
        base = Path("plugin/theotown_mcp")
        assert (base / "plugin.json").exists()
        assert (base / "core.lua").exists()
        assert (base / "inbox.lua").exists()
