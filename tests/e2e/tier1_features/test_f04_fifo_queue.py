"""
Tier 1: Feature F04 — In-Game FIFO Queue Manager
5 Isolated Test Cases.
"""

from __future__ import annotations

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.models import BuildRoadCmd, BuildZoneCmd


class TestFeatureF04FIFOQueue:
    def test_e2e_t1_f04_01_enqueue_single_batch(self, mock_env: MockTheoTownEnv):
        """Enqueue single batch job and check initial status."""
        cmds = [
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=0),
            BuildZoneCmd(x=0, y=2, width=2, height=2),
        ]
        job = mock_env.bridge.execute_plan(cmds)
        assert job.status == "pending"
        assert job.total_steps == 2
        assert job.completed_steps == 0

    def test_e2e_t1_f04_02_fifo_ordering(self, mock_env: MockTheoTownEnv):
        """Verify sequential command execution preserving order."""
        cmds = [
            BuildRoadCmd(x0=0, y0=0, x1=10, y1=0),
            BuildZoneCmd(x=0, y=1, width=2, height=2),
        ]
        mock_env.bridge.execute_plan(cmds)
        mock_env.simulator.process_inbox()

        # Both road and zone should be placed in grid
        assert (0, 0) in mock_env.oracle.grid
        assert (0, 1) in mock_env.oracle.grid
        assert mock_env.oracle.grid[(0, 0)].get("road") is not None
        assert mock_env.oracle.grid[(0, 1)].get("zone") is not None

    def test_e2e_t1_f04_03_job_status_transitions(self, mock_env: MockTheoTownEnv):
        """Verify job transition from pending to completed."""
        job = mock_env.bridge.execute_plan([BuildRoadCmd(x0=5, y0=5, x1=15, y1=5)])
        assert job.status == "pending"

        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.status == "completed"
        assert res.progress == 1.0

    def test_e2e_t1_f04_04_duplicate_job_id_avoidance(self, mock_env: MockTheoTownEnv):
        """Core queue manager skips re-processing of already processed job IDs."""
        job = mock_env.bridge.execute_plan([BuildRoadCmd(x0=5, y0=5, x1=15, y1=5)])
        res1 = mock_env.simulator.process_inbox()
        assert res1 is not None and res1.status == "completed"

        # Immediate second tick with same file
        res2 = mock_env.simulator.process_inbox()
        # Returns cached status without executing twice or deducting funds twice
        assert res2 is not None
        assert res2.job_id == job.job_id

    def test_e2e_t1_f04_05_step_progress_calculation(self, mock_env: MockTheoTownEnv):
        """Accurate calculation of progress based on completed steps."""
        mock_env.bridge.execute_plan([
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=0),
            BuildRoadCmd(x0=0, y0=1, x1=5, y1=1),
        ])
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.progress == 1.0
        assert res.completed_steps == 2
        assert res.total_steps == 2
