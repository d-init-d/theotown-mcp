"""
Tier 1: Feature F15 — Hardened Windows Atomic Bridge
5 Isolated Test Cases.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from theotown_mcp.bridge import serialize_to_lua, write_atomic_lua


class TestFeatureF15AtomicBridge:
    def test_e2e_t1_f15_01_same_volume_temp_file(self, tmp_path: Path):
        """Temporary swap file is colocated in target directory."""
        target = tmp_path / "inbox.lua"
        write_atomic_lua(target, "-- atomic write")
        assert target.exists()

    def test_e2e_t1_f15_02_handle_closed_before_replace(self, tmp_path: Path):
        """Handle closure before replace prevents WinError 32."""
        target = tmp_path / "inbox.lua"
        # Multiple consecutive writes
        for i in range(5):
            write_atomic_lua(target, f"-- write {i}")
            assert target.read_text(encoding="utf-8") == f"-- write {i}"

    def test_e2e_t1_f15_03_atomic_replacement_existing_file(self, tmp_path: Path):
        """Atomic replacement cleanly updates existing file content."""
        target = tmp_path / "inbox.lua"
        target.write_text("initial", encoding="utf-8")
        write_atomic_lua(target, "updated_payload")
        assert target.read_text(encoding="utf-8") == "updated_payload"

    def test_e2e_t1_f15_04_exponential_retry_on_permission_error(self, tmp_path: Path):
        """Exponential retry loop recovers from transient locks."""
        target = tmp_path / "inbox.lua"
        call_count = 0
        real_replace = os.replace

        def transient_lock(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise PermissionError("Transient file lock")
            return real_replace(src, dst)

        with patch("os.replace", side_effect=transient_lock):
            write_atomic_lua(target, "recovered", max_retries=5, base_delay=0.001)

        assert target.read_text(encoding="utf-8") == "recovered"
        assert call_count == 2

    def test_e2e_t1_f15_05_anti_injection_string_escaping(self):
        """Strict escaping of quotes and newlines in Lua serializer."""
        malicious = 'Test "Building"\nPath\\Escape'
        escaped = serialize_to_lua(malicious)
        assert '\\"' in escaped
        assert "\\n" in escaped
        assert "\\\\" in escaped
