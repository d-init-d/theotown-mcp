"""Tier 1: static compatibility file and JSON mailbox tests."""

from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.lua_syntax_check import check_lua_syntax


class TestFeatureF10InboxTemplate:
    def test_e2e_t1_f10_01_default_template_structure(self):
        """The legacy file is inert and cannot mutate game state."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        assert inbox_file.exists()
        content = inbox_file.read_text(encoding="utf-8")
        assert "requests.txt" in content
        assert "Builder." not in content

    def test_e2e_t1_f10_02_clean_syntax(self):
        """Parse inbox.lua with Lua syntax validator."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        clean, msg = check_lua_syntax(inbox_file)
        assert clean, msg

    def test_e2e_t1_f10_03_storage_null_safety(self):
        """Ensure the compatibility file contains no executable mailbox logic."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        content = inbox_file.read_text(encoding="utf-8")
        assert "TheoTown.getStorage" not in content

    def test_e2e_t1_f10_04_overwrite_safety(self, mock_env: MockTheoTownEnv):
        """Speed commands are appended as JSON and never rewrite Lua source."""
        mock_env.bridge.set_speed(1)
        mailbox = json.loads(mock_env.config.requests_path.read_text(encoding="utf-8"))
        job = next(reversed(mailbox["jobs"].values()))
        assert job["commands"] == {"1": {"cmd": "set_speed", "speed": 1}}

    def test_e2e_t1_f10_05_utf8_no_bom(self):
        """Verify inbox.lua has no UTF-8 BOM preamble."""
        inbox_file = Path("plugin/theotown_mcp/inbox.lua")
        raw_bytes = inbox_file.read_bytes()
        assert not raw_bytes.startswith(b"\xef\xbb\xbf")
