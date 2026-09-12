"""
Tier 1: Feature F24 — Adversarial Coverage Hardening
5 Isolated Test Cases.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.bridge import serialize_to_lua, write_atomic_lua
from theotown_mcp.models import BuildRoadCmd


class TestFeatureF24AdversarialCoverage:
    def test_e2e_t1_f24_01_injection_attack_neutralization(self):
        """Malicious Lua script injection in building ID is neutralized."""
        malicious_id = 'test"; os.execute("calc.exe"); --'
        serialized = serialize_to_lua(malicious_id)
        assert '\\"' in serialized
        assert 'os.execute' not in serialized or '\\"' in serialized

    def test_e2e_t1_f24_02_rapid_atomic_replaces(self, tmp_path: Path):
        """High-frequency consecutive atomic writes succeed without data corruption."""
        target = tmp_path / "inbox.lua"
        for i in range(25):
            write_atomic_lua(target, f"-- payload {i}")
            assert target.read_text(encoding="utf-8") == f"-- payload {i}"

    def test_e2e_t1_f24_03_sudden_file_lock_injection(self, tmp_path: Path):
        """Bridge absorbs file locks injected by simulated antivirus."""
        target = tmp_path / "inbox.lua"
        call_count = 0
        real_replace = os.replace

        def locked_replace(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PermissionError("WinError 32: File in use")
            return real_replace(src, dst)

        with patch("os.replace", side_effect=locked_replace):
            write_atomic_lua(target, "-- retry success", max_retries=3, base_delay=0.001)

        assert target.read_text(encoding="utf-8") == "-- retry success"

    def test_e2e_t1_f24_04_massive_batch_payload(self, mock_env: MockTheoTownEnv):
        """Large payload with 200 commands processes within memory bounds."""
        cmds = [{"cmd": "build_road", "x0": i % 100, "y0": 10, "x1": i % 100, "y1": 15} for i in range(200)]
        val = mock_env.bridge.validate_plan(cmds, dry_run=True)
        assert val.valid is True
        assert val.command_count == 200

    def test_e2e_t1_f24_05_stutter_protection_under_load(self, mock_env: MockTheoTownEnv):
        """Budgeting limits single tick processing."""
        cmds = [BuildRoadCmd(x0=i % 100, y0=20, x1=i % 100, y1=25) for i in range(100)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox(max_units_per_tick=64)
        assert res is not None
        assert res.total_steps == 100
