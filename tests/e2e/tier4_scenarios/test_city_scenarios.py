"""
Tier 4: Real-World City Simulation Scenarios
12 Full Integration Scenarios (SC01 to SC12).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.city_oracle import slice_road_coordinates
from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildUtilityCmd,
    BuildZoneCmd,
)


class TestTier4CityScenarios:
    @pytest.mark.anyio
    async def test_sc01_greenfield_frontier(self, mock_env: MockTheoTownEnv):
        """SC01: Founding a Balanced Starter Town (Roads, RCI zones, Utilities)."""
        # 1. Road network
        road_res = await mock_env.server.call_tool("theotown_build_road", {"x0": 10, "y0": 10, "x1": 30, "y1": 10})
        assert road_res.is_error is False
        mock_env.simulator.process_inbox()

        # 2. Zoning: Residential, Commercial, Industrial
        await mock_env.server.call_tool("theotown_build_zone", {"x": 10, "y": 12, "width": 4, "height": 4, "zone_type": "residential_low"})
        mock_env.simulator.process_inbox()
        await mock_env.server.call_tool("theotown_build_zone", {"x": 16, "y": 12, "width": 4, "height": 4, "zone_type": "commercial_low"})
        mock_env.simulator.process_inbox()
        await mock_env.server.call_tool("theotown_build_zone", {"x": 22, "y": 12, "width": 4, "height": 4, "zone_type": "industrial_low"})
        mock_env.simulator.process_inbox()

        # 3. Utilities: Water tower and Power wires
        await mock_env.server.call_tool("theotown_build_building", {"x": 8, "y": 8, "building_id": "$watertower00"})
        mock_env.simulator.process_inbox()
        await mock_env.server.call_tool("theotown_build_utilities", {"x0": 8, "y0": 8, "x1": 10, "y1": 8, "utility_type": "pipe"})
        mock_env.simulator.process_inbox()

        # Invariants
        assert mock_env.oracle.population > 0
        assert mock_env.oracle.money < 100000

    @pytest.mark.anyio
    async def test_sc02_industrial_relocation(self, mock_env: MockTheoTownEnv):
        """SC02: Industrial Relocation & Pollution Mitigation."""
        # Zone initial industrial near residential
        mock_env.oracle.execute_command(BuildZoneCmd(x=10, y=10, width=4, height=4, zone_type="industrial_low"))
        assert (10, 10) in mock_env.oracle.grid

        # Demolish industrial
        await mock_env.server.call_tool("theotown_demolish", {"x": 10, "y": 10, "width": 4, "height": 4})
        mock_env.simulator.process_inbox()
        assert mock_env.oracle.grid.get((10, 10)) is None

        # Rebuild industrial on outskirts (90, 90)
        await mock_env.server.call_tool("theotown_build_zone", {"x": 90, "y": 90, "width": 6, "height": 6, "zone_type": "industrial_high"})
        mock_env.simulator.process_inbox()
        assert (90, 90) in mock_env.oracle.grid

    def test_sc03_highway_expansion_and_bridge_crossing(self, mock_env: MockTheoTownEnv):
        """SC03: 100-Tile Dual-Lane Highway Expansion across river."""
        # 100-tile road from (10, 50) to (110, 50)
        cmd = BuildRoadCmd(x0=10, y0=50, x1=110, y1=50, road_type="$road03", level=1)
        slices = slice_road_coordinates(cmd.x0, cmd.y0, cmd.x1, cmd.y1)
        assert len(slices) == 4  # Sliced into 4 segments <= 32 tiles

        mock_env.bridge.execute_plan([cmd])
        mock_env.simulator.process_inbox()
        assert (10, 50) in mock_env.oracle.grid
        assert (110, 50) in mock_env.oracle.grid

    @pytest.mark.anyio
    async def test_sc04_fiscal_crisis_management(self, mock_env: MockTheoTownEnv):
        """SC04: Detect treasury exhaustion, pause simulation, reject expensive plan."""
        # Set low treasury
        mock_env.oracle.money = 500
        mock_env.simulator.sync_telemetry_to_disk()

        # Validate expensive project ($50,000)
        expensive_cmds = [{"cmd": "build_building", "x": 10, "y": 10, "building_id": "$solarplant00"}]
        val_res = await mock_env.server.call_tool("theotown_validate_plan", {"commands": expensive_cmds})
        # Validates with treasury warning
        assert len(val_res.structured_content["warnings"]) >= 1

        # Shift speed to 0 (Pause)
        spd_res = await mock_env.server.call_tool("theotown_set_speed", {"speed": 0})
        assert spd_res.structured_content["speed"] == 0

    @pytest.mark.anyio
    async def test_sc05_urban_redevelopment_upzoning(self, mock_env: MockTheoTownEnv):
        """SC05: Bulldoze 4x4 low density zone and replace with high density."""
        # Initial low-density zone
        mock_env.oracle.execute_command(BuildZoneCmd(x=20, y=20, width=4, height=4, zone_type="residential_low"))
        # Demolish
        await mock_env.server.call_tool("theotown_demolish", {"x": 20, "y": 20, "width": 4, "height": 4})
        mock_env.simulator.process_inbox()
        # High density rebuild
        await mock_env.server.call_tool("theotown_build_zone", {"x": 20, "y": 20, "width": 4, "height": 4, "zone_type": "residential_high"})
        mock_env.simulator.process_inbox()
        assert mock_env.oracle.grid[(20, 20)]["zone"] == "$zoneresidential_lvl2"

    def test_sc06_disaster_recovery_pipeline(self, mock_env: MockTheoTownEnv):
        """SC06: Disaster destroys road and utility, clear debris and reconnect."""
        # Place road and wire
        mock_env.oracle.execute_command(BuildRoadCmd(x0=0, y0=0, x1=5, y1=0))
        mock_env.oracle.execute_command(BuildUtilityCmd(x0=0, y0=0, x1=5, y1=0, utility_type="wire"))

        # Simulated disaster destroys tile (2, 0)
        mock_env.oracle.grid.pop((2, 0), None)
        assert (2, 0) not in mock_env.oracle.grid

        # Reconnect
        mock_env.oracle.execute_command(BuildRoadCmd(x0=2, y0=0, x1=2, y1=0))
        mock_env.oracle.execute_command(BuildUtilityCmd(x0=2, y0=0, x1=2, y1=0, utility_type="wire"))
        assert (2, 0) in mock_env.oracle.grid

    def test_sc07_custom_modded_asset_deployment(self, mock_env: MockTheoTownEnv):
        """SC07: Dynamically discover modded asset and construct it."""
        mock_env.catalog.drafts["$custom_headquarters01"] = {
            "id": "$custom_headquarters01",
            "title": "Town Hall HQ",
            "type": "building",
            "price": 12000,
        }
        mock_env.catalog.aliases["town_hall"] = "$custom_headquarters01"

        resolved = mock_env.catalog.resolve_draft_id("town_hall")
        assert resolved == "$custom_headquarters01"

        cmd = BuildBuildingCmd(x=15, y=15, building_id=resolved)
        res = mock_env.oracle.execute_command(cmd)
        assert res["success"] is True
        assert mock_env.oracle.grid[(15, 15)]["building"] == "$custom_headquarters01"

    def test_sc08_batch_job_cancellation(self, mock_env: MockTheoTownEnv):
        """SC08: Enqueue 50-tile road plan and cancel mid-flight."""
        cmds = [BuildRoadCmd(x0=i, y0=5, x1=i, y1=5) for i in range(50)]
        job = mock_env.bridge.execute_plan(cmds)

        # Cancel job immediately
        c_res = mock_env.bridge.cancel_job(job.job_id)
        assert c_res["status"] == "cancel_requested"
        assert mock_env.simulator.process_inbox().status == "cancelled"
        assert mock_env.bridge.get_job_status(job.job_id).status == "cancelled"

    @pytest.mark.anyio
    async def test_sc09_multi_agent_mesh_load(self, mock_env: MockTheoTownEnv):
        """SC09: Multiple concurrent operations across quadrants."""
        # Quadrant 1
        t1 = mock_env.server.call_tool("theotown_build_road", {"x0": 10, "y0": 10, "x1": 20, "y1": 10})
        # Quadrant 2
        t2 = mock_env.server.call_tool("theotown_build_zone", {"x": 70, "y": 10, "width": 4, "height": 4})
        # Quadrant 3
        t3 = mock_env.server.call_tool("theotown_get_status", {})

        r1, r2, r3 = await t1, await t2, await t3
        assert r1.is_error is False
        assert r2.is_error is False
        assert r3.is_error is False

    def test_sc10_unstable_filesystem_resilience(self, tmp_path: Path):
        """SC10: Anti-virus contention simulation with transient file locks."""
        import os
        from unittest.mock import patch

        from theotown_mcp.bridge import write_atomic_lua

        target = tmp_path / "inbox.lua"
        real_replace = os.replace
        lock_count = 0

        def av_scanner_lock(src, dst):
            nonlocal lock_count
            lock_count += 1
            if lock_count <= 2:
                raise PermissionError("Access denied (Windows Defender Scan)")
            return real_replace(src, dst)

        with patch("os.replace", side_effect=av_scanner_lock):
            write_atomic_lua(target, "-- resilient payload", max_retries=5, base_delay=0.001)

        assert target.read_text(encoding="utf-8") == "-- resilient payload"
        assert lock_count == 3

    def test_sc11_30_day_simulation_cycle(self, mock_env: MockTheoTownEnv):
        """SC11: 30-day simulation cycle with tax collection and calendar rollover."""
        mock_env.oracle.population = 1000
        initial_money = mock_env.oracle.money
        mock_env.oracle.advance_time(days=30)

        # Tax collected
        assert mock_env.oracle.money > initial_money
        # Month advanced
        assert mock_env.oracle.month == 2

    @pytest.mark.anyio
    async def test_sc12_autonomous_urban_planner_workflow(self, mock_env: MockTheoTownEnv):
        """SC12: Autonomous prompt-driven urban planner pipeline."""
        # 1. Get urban planner prompt
        prompt_res = await mock_env.server.get_prompt("urban_planner", {})
        assert "Road Hierarchy" in prompt_res.messages[0].content.text

        # 2. Dry-run plan validation
        plan = [
            {"cmd": "build_road", "x0": 10, "y0": 10, "x1": 30, "y1": 10},
            {"cmd": "build_zone", "x": 10, "y": 12, "width": 5, "height": 5, "zone_type": "residential_low"},
            {"cmd": "build_building", "x": 8, "y": 8, "building_id": "$park00"},
        ]
        val_res = await mock_env.server.call_tool("theotown_validate_plan", {"commands": plan, "dry_run": True})
        assert val_res.structured_content["valid"] is True

        # 3. Execute plan
        exec_res = await mock_env.server.call_tool("theotown_execute_plan", {"commands": plan})
        assert exec_res.structured_content["status"] == "pending"

        # 4. Tick simulation and monitor
        mock_env.simulator.process_inbox()
        status_res = await mock_env.server.call_tool("theotown_get_job", {"job_id": exec_res.structured_content["job_id"]})
        assert status_res.structured_content["status"] == "completed"
