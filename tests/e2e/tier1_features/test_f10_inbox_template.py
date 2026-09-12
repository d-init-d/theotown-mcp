"""
Tier 1: Feature F10 — Inbox Template Script
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.lua_syntax_check import check_lua_syntax


class TestFeatureF10InboxTemplate:
    def test_e2e_t1_f10_01_default_template_structure(self):
        """Validate structure of plugin/theotown_mcp/inbox.lua."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        assert inbox_file.exists()
        content = inbox_file.read_text(encoding="utf-8")
        assert "TheoTown.getStorage()" in content
        assert "script:init()" in content

    def test_e2e_t1_f10_02_clean_syntax(self):
        """Parse inbox.lua with Lua syntax validator."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        clean, msg = check_lua_syntax(inbox_file)
        assert clean, msg

    def test_e2e_t1_f10_03_storage_null_safety(self):
        """Ensure storage is checked before indexing in inbox.lua."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        content = inbox_file.read_text(encoding="utf-8")
        assert "if storage then" in content

    def test_e2e_t1_f10_04_overwrite_safety(self, mock_env: MockTheoTownEnv):
        """Atomic write cleanly replaces inbox.lua without remnants."""
        mock_env.config.inbox_path.write_text("-- original", encoding="utf-8")
        mock_env.bridge.set_speed(1)
        new_content = mock_env.config.inbox_path.read_text(encoding="utf-8")
        assert "City.setSpeed(1)" in new_content
        assert "-- original" not in new_content

    def test_e2e_t1_f10_05_utf8_no_bom(self):
        """Verify inbox.lua has no UTF-8 BOM preamble."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        raw_bytes = inbox_file.read_bytes()
        assert not raw_bytes.startswith(b"\xef\xbb\xbf")
