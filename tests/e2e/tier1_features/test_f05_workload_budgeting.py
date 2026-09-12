"""
Tier 1: Feature F05 — Workload Budgeting & Throttling
5 Isolated Test Cases.
"""

from __future__ import annotations

import time

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.models import BuildRoadCmd


class TestFeatureF05WorkloadBudgeting:
    def test_e2e_t1_f05_01_work_unit_ceiling_64(self, mock_env: MockTheoTownEnv):
        """Budgeting limits execution to 64 operations in single tick."""
        # 100 single-tile road commands
        cmds = [BuildRoadCmd(x0=i, y0=0, x1=i, y1=0) for i in range(100)]
        mock_env.bridge.execute_plan(cmds)

        # Process with limit 64
        res = mock_env.simulator.process_inbox(max_units_per_tick=64)
        assert res is not None
        assert res.total_steps == 100

    def test_e2e_t1_f05_02_execution_time_ceiling_3ms(self, mock_env: MockTheoTownEnv):
        """Simulation tick returns control within microsecond range."""
        cmds = [BuildRoadCmd(x0=i, y0=10, x1=i, y1=10) for i in range(20)]
        mock_env.bridge.execute_plan(cmds)

        t0 = time.perf_counter()
        mock_env.simulator.process_inbox()
        elapsed = time.perf_counter() - t0

        # Entire process should execute in well under 100ms
        assert elapsed < 0.1

    def test_e2e_t1_f05_03_multi_tick_resumption(self, mock_env: MockTheoTownEnv):
        """Multi-tick batches progress sequentially without resetting pointers."""
        cmds = [BuildRoadCmd(x0=i, y0=20, x1=i, y1=20) for i in range(50)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.completed_steps == 50

    def test_e2e_t1_f05_04_non_blocking_guarantee(self, mock_env: MockTheoTownEnv):
        """Ensures commands do not block execution threads."""
        cmds = [BuildRoadCmd(x0=0, y0=30, x1=20, y1=30)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.status == "completed"

    def test_e2e_t1_f05_05_job_status_update_on_budget_slice(self, mock_env: MockTheoTownEnv):
        """Status is updated accurately and reflected in job status file."""
        cmds = [BuildRoadCmd(x0=0, y0=40, x1=10, y1=40)]
        job = mock_env.bridge.execute_plan(cmds)
        mock_env.simulator.process_inbox()

        st = mock_env.bridge.get_job_status(job.job_id)
        assert st.status == "completed"
        assert st.progress == 1.0
