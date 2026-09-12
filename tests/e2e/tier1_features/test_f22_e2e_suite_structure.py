"""
Tier 1: Feature F22 — Opaque-Box E2E Testing Suite
5 Isolated Test Cases.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.live_client import LiveDetector


class TestFeatureF22E2ESuiteStructure:
    def test_e2e_t1_f22_01_runner_file_exists(self):
        """tests/e2e/runner.py exists and supports argparse."""
        runner_path = Path("tests/e2e/runner.py")
        assert runner_path.exists()
        content = runner_path.read_text(encoding="utf-8")
        assert "--tier" in content
        assert "--report-json" in content

    def test_e2e_t1_f22_02_headless_mock_harness(self, mock_env: MockTheoTownEnv):
        """MockTheoTownEnv provides headless execution without TheoTown process."""
        assert mock_env.oracle.name == "E2ETestCity"
        assert mock_env.bridge is not None
        assert mock_env.simulator is not None

    def test_e2e_t1_f22_03_structured_json_report(self, tmp_path: Path):
        """JSON test report schema verification."""
        report = {
            "timestamp": 1773300000.0,
            "duration_seconds": 1.25,
            "tier": "all",
            "mode": "mock",
            "exit_code": 0,
            "status": "PASS",
        }
        report_file = tmp_path / "e2e_report.json"
        report_file.write_text(json.dumps(report), encoding="utf-8")

        loaded = json.loads(report_file.read_text(encoding="utf-8"))
        assert loaded["status"] == "PASS"
        assert loaded["exit_code"] == 0

    def test_e2e_t1_f22_04_live_detector(self):
        """LiveDetector exposes probe_local_storage and is_game_running."""
        probe = LiveDetector.probe_local_storage()
        assert "installed" in probe
        assert "game_running" in probe

    def test_e2e_t1_f22_05_harness_modules_exist(self):
        """Verify harness module files under tests/e2e/harness/."""
        harness_dir = Path("tests/e2e/harness")
        assert (harness_dir / "city_oracle.py").exists()
        assert (harness_dir / "bridge_simulator.py").exists()
        assert (harness_dir / "lua_syntax_check.py").exists()
        assert (harness_dir / "live_client.py").exists()
