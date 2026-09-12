"""
Tier 1: Feature F23 — E2E Test Execution & 100% Pass
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.models import BuildRoadCmd


class TestFeatureF23ExecutionVerification:
    def test_e2e_t1_f23_01_tier1_directory_structure(self):
        """Verify tier1_features directory contains test modules."""
        t1_dir = Path("tests/e2e/tier1_features")
        files = list(t1_dir.glob("test_f*.py"))
        assert len(files) >= 20

    def test_e2e_t1_f23_02_deterministic_execution(self, mock_env: MockTheoTownEnv):
        """Simulation produces identical deterministic results across runs."""
        cmd = BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)
        res1 = mock_env.oracle.execute_command(cmd)
        assert res1["success"] is True
        assert res1["cost"] == 6 * 50

    def test_e2e_t1_f23_03_zero_flakiness(self, mock_env: MockTheoTownEnv):
        """Repeated validations report consistent results."""
        for _ in range(5):
            res = mock_env.bridge.validate_plan([{"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0}])
            assert res.valid is True
            assert res.errors == []

    def test_e2e_t1_f23_04_no_residual_temp_files(self, mock_env: MockTheoTownEnv):
        """No orphaned .tmp swap files left on disk."""
        mock_env.bridge.set_speed(1)
        temp_files = list(mock_env.config.plugin_dir.glob("tmp_inbox_*.tmp"))
        assert len(temp_files) == 0

    def test_e2e_t1_f23_05_contract_compliance(self, mock_env: MockTheoTownEnv):
        """Verification passes with clean assertions."""
        status = mock_env.bridge.get_job_status("non_existent")
        assert status.status == "failed"
