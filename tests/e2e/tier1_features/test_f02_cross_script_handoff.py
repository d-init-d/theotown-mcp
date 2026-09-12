"""
Tier 1: Feature F02 — Phase 0 Cross-Script Handoff & Telemetry
5 Isolated Test Cases.
"""

from __future__ import annotations

import json

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.models import BuildRoadCmd, CityTelemetry


class TestFeatureF02CrossScriptHandoff:
    def test_e2e_t1_f02_01_cross_script_deposit(self, mock_env: MockTheoTownEnv):
        """Cross-script deposit into simulated storage and pick up by core listener."""
        cmd = BuildRoadCmd(x0=10, y0=10, x1=20, y1=10)
        job = mock_env.bridge.execute_plan([cmd])

        assert job.status == "pending"
        # Simulator processes inbox
        mock_env.simulator.process_inbox()

        # Core should have marked job completed
        status = mock_env.bridge.get_job_status(job.job_id)
        assert status.status == "completed"
        assert status.completed_steps == 1

    def test_e2e_t1_f02_02_telemetry_json_generation(self, mock_env: MockTheoTownEnv):
        """Telemetry JSON file creation with valid schema."""
        mock_env.oracle.money = 88000
        mock_env.oracle.population = 1500
        mock_env.simulator.sync_telemetry_to_disk()

        telemetry_file = mock_env.config.telemetry_path
        assert telemetry_file.exists()
        raw = json.loads(telemetry_file.read_text(encoding="utf-8"))
        assert raw["money"] == 88000
        assert raw["population"] == 1500

    def test_e2e_t1_f02_03_bridge_read_telemetry(self, mock_env: MockTheoTownEnv):
        """Python bridge reads and deserializes telemetry into CityTelemetry model."""
        mock_env.oracle.name = "Atlantis"
        mock_env.simulator.sync_telemetry_to_disk()

        telem = mock_env.bridge.read_telemetry()
        assert isinstance(telem, CityTelemetry)
        assert telem.connected is True
        assert telem.name == "Atlantis"

    def test_e2e_t1_f02_04_job_status_handoff(self, mock_env: MockTheoTownEnv):
        """Job status handoff from simulated core engine to Python bridge."""
        job_file = mock_env.config.plugin_dir / "job_handoff_01.json"
        status_data = {
            "job_id": "handoff_01",
            "status": "running",
            "progress": 0.5,
            "total_steps": 10,
            "completed_steps": 5,
            "created_at": 100.0,
            "updated_at": 105.0,
        }
        job_file.write_text(json.dumps(status_data), encoding="utf-8")

        status = mock_env.bridge.get_job_status("handoff_01")
        assert status.status == "running"
        assert status.progress == 0.5
        assert status.completed_steps == 5

    def test_e2e_t1_f02_05_simulation_speed_telemetry_sync(self, mock_env: MockTheoTownEnv):
        """Simulation speed telemetry reflects active game speed."""
        mock_env.oracle.speed = 3
        mock_env.simulator.sync_telemetry_to_disk()

        telem = mock_env.bridge.read_telemetry()
        assert telem.speed == 3
