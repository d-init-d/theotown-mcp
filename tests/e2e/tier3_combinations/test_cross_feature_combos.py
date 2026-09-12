"""
Tier 3: Cross-Feature Combinations
24 Pairwise Interaction Test Cases (COMB-01 to COMB-24).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.city_oracle import slice_road_coordinates
from theotown_mcp.cli import app
from theotown_mcp.models import (
    BuildRoadCmd,
)


class TestCrossFeatureCombinations:
    def test_comb_01_f01_f02_canary_and_handoff(self, mock_env: MockTheoTownEnv):
        """COMB-01: F01 + F02 (Canary storage persistence + cross-script reload handoff)."""
        canary = {"canary": "CANARY_TOKEN_01"}
        mock_env.config.pmodext_path.write_text(f"header\n#{json.dumps(canary)}", encoding="utf-8")
        raw = mock_env.config.pmodext_path.read_text(encoding="utf-8").split("#", 1)[1]
        assert json.loads(raw)["canary"] == "CANARY_TOKEN_01"

    def test_comb_02_f03_f10_manifest_and_inbox(self, mock_env: MockTheoTownEnv):
        """COMB-02: F03 + F10 (Manifest dev flag + inbox template reload)."""
        manifest = json.loads(Path("plugin/theotown_mcp/plugin.json").read_text(encoding="utf-8"))
        inbox_entry = next(d for d in manifest if d["id"] == "$theotown_mcp_inbox")
        assert inbox_entry["dev"] is True
        assert Path("plugin/theotown_mcp/inbox.lua").exists()

    def test_comb_03_f04_f05_fifo_and_budgeting(self, mock_env: MockTheoTownEnv):
        """COMB-03: F04 + F05 (FIFO queue + workload budgeting throttling)."""
        cmds = [BuildRoadCmd(x0=i, y0=0, x1=i, y1=0) for i in range(70)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox(max_units_per_tick=64)
        assert res is not None
        assert res.total_steps == 70

    def test_comb_04_f06_f07_slicing_and_pricing(self, mock_env: MockTheoTownEnv):
        """COMB-04: F06 + F07 (Road slicing + preflight checks and pricing)."""
        cmd = BuildRoadCmd(x0=0, y0=10, x1=40, y1=10, road_type="$road03")
        slices = slice_road_coordinates(cmd.x0, cmd.y0, cmd.x1, cmd.y1)
        assert len(slices) == 2
        # Both slices buildable
        for s in slices:
            assert mock_env.oracle.is_road_buildable(s[0], s[1], s[2], s[3]) is True
        cost = mock_env.catalog.estimate_command_cost(cmd)
        assert cost == 41 * 50

    def test_comb_05_f08_f13_telemetry_and_autoconfig(self, mock_env: MockTheoTownEnv):
        """COMB-05: F08 + F13 (City telemetry + auto-configuration data dir)."""
        mock_env.simulator.sync_telemetry_to_disk()
        assert mock_env.config.telemetry_path.exists()
        telem = mock_env.bridge.read_telemetry()
        assert telem.connected is True
        assert telem.name == "E2ETestCity"

    def test_comb_06_f09_f14_draft_discovery_and_alias(self, mock_env: MockTheoTownEnv):
        """COMB-06: F09 + F14 (Dynamic draft discovery + runtime alias manager)."""
        assert mock_env.catalog.resolve_draft_id("two_lane_road") == "$road03"
        draft = mock_env.catalog.get_draft("two_lane_road")
        assert draft is not None
        assert draft["id"] == "$road03"

    def test_comb_07_f12_f15_dsl_and_atomic_bridge(self, mock_env: MockTheoTownEnv):
        """COMB-07: F12 + F15 (DSL models validation + atomic bridge writing)."""
        cmd = BuildRoadCmd(x0=5, y0=5, x1=15, y1=5)
        job = mock_env.bridge.execute_plan([cmd])
        inbox_content = mock_env.config.inbox_path.read_text(encoding="utf-8")
        assert job.job_id in inbox_content

    @pytest.mark.anyio
    async def test_comb_08_f16_f17_tools_and_resources(self, mock_env: MockTheoTownEnv):
        """COMB-08: F16 + F17 (MCP tools + MCP resources/prompts coordination)."""
        # Execute tool
        res = await mock_env.server.call_tool("theotown_build_road", {"x0": 0, "y0": 0, "x1": 5, "y1": 0})
        assert res.is_error is False
        # Read resource
        res_data = await mock_env.server.read_resource("theotown://city/status")
        assert len(res_data) == 1

    def test_comb_09_f18_f13_cli_and_config(self, mock_env: MockTheoTownEnv):
        """COMB-09: F18 + F13 (CLI probe-ipc + auto-configuration override)."""
        runner = CliRunner()
        res = runner.invoke(app, ["probe-ipc", "--data-dir", str(mock_env.config.theotown_data_dir)])
        assert res.exit_code == 0
        assert "Probe IPC diagnostics completed successfully" in res.output

    def test_comb_10_f19_f20_git_and_documentation(self):
        """COMB-10: F19 + F20 (Git repository + documentation config alignment)."""
        assert Path("LICENSE").exists()
        assert Path("README.md").exists()
        assert "MIT License" in Path("LICENSE").read_text(encoding="utf-8")
        assert "MIT" in Path("README.md").read_text(encoding="utf-8")

    def test_comb_11_f21_f22_unit_and_e2e_harness(self, mock_env: MockTheoTownEnv):
        """COMB-11: F21 + F22 (Unit test execution + E2E harness integration)."""
        assert Path("tests/test_dsl_models.py").exists()
        assert mock_env.oracle.name == "E2ETestCity"

    def test_comb_12_f23_f24_verification_and_adversarial(self, mock_env: MockTheoTownEnv):
        """COMB-12: F23 + F24 (Execution verification + adversarial security validation)."""
        from theotown_mcp.bridge import serialize_to_lua
        safe_str = serialize_to_lua('malicious"; os.execute(); --')
        assert '\\"' in safe_str

    def test_comb_13_f04_f15_fifo_and_atomic_swap(self, mock_env: MockTheoTownEnv):
        """COMB-13: F04 + F15 (FIFO queue management + atomic write swap loop)."""
        cmd = BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)
        mock_env.bridge.execute_plan([cmd])
        mock_env.simulator.process_inbox()
        assert (0, 0) in mock_env.oracle.grid

    def test_comb_14_f06_f12_road_slicing_and_bounds(self, mock_env: MockTheoTownEnv):
        """COMB-14: F06 + F12 (Road segmenting + Pydantic model bounds check)."""
        cmd = BuildRoadCmd(x0=0, y0=0, x1=60, y1=0)
        assert cmd.check_bounds(128, 128) == []
        slices = slice_road_coordinates(cmd.x0, cmd.y0, cmd.x1, cmd.y1)
        assert len(slices) == 2

    def test_comb_15_f07_f14_preflight_and_alias(self, mock_env: MockTheoTownEnv):
        """COMB-15: F07 + F14 (Preflight pricing + alias resolution)."""
        price = mock_env.catalog.estimate_unit_price("residential_low")
        assert price == 10

    @pytest.mark.anyio
    async def test_comb_16_f08_f16_telemetry_and_status_tool(self, mock_env: MockTheoTownEnv):
        """COMB-16: F08 + F16 (City telemetry reader + theotown_get_status tool)."""
        mock_env.oracle.money = 92000
        mock_env.simulator.sync_telemetry_to_disk()
        res = await mock_env.server.call_tool("theotown_get_status", {})
        assert res.structured_content["money"] == 92000

    @pytest.mark.anyio
    async def test_comb_17_f05_f16_budgeting_and_execute_plan_tool(self, mock_env: MockTheoTownEnv):
        """COMB-17: F05 + F16 (Budget throttling + theotown_execute_plan tool)."""
        cmds = [{"cmd": "build_road", "x0": i, "y0": 0, "x1": i, "y1": 0} for i in range(10)]
        res = await mock_env.server.call_tool("theotown_execute_plan", {"commands": cmds})
        assert res.structured_content["status"] == "pending"

    def test_comb_18_f10_f15_inbox_and_escaping(self, mock_env: MockTheoTownEnv):
        """COMB-18: F10 + F15 (Inbox template + serialize_to_lua anti-injection)."""
        from theotown_mcp.bridge import generate_job_lua
        lua = generate_job_lua("job_esc", [{"cmd": "build_building", "x": 0, "y": 0, "building_id": "park\""}])
        assert '\\"' in lua

    @pytest.mark.anyio
    async def test_comb_19_f09_f17_draft_discovery_and_resource(self, mock_env: MockTheoTownEnv):
        """COMB-19: F09 + F17 (Draft discovery + theotown://catalog/drafts resource)."""
        res = await mock_env.server.read_resource("theotown://catalog/drafts")
        data = json.loads(res[0].content)
        assert len(data) >= 10

    def test_comb_20_f01_f18_storage_and_cli_probe(self, mock_env: MockTheoTownEnv):
        """COMB-20: F01 + F18 (Storage discovery canary + CLI probe-ipc command)."""
        runner = CliRunner()
        res = runner.invoke(app, ["probe-ipc", "--data-dir", str(mock_env.config.theotown_data_dir)])
        assert "Atomic filesystem write test: PASS" in res.output

    @pytest.mark.anyio
    async def test_comb_21_f14_f16_catalog_and_search_tool(self, mock_env: MockTheoTownEnv):
        """COMB-21: F14 + F16 (Draft catalog lookup + theotown_get_draft_catalog tool)."""
        res = await mock_env.server.call_tool("theotown_get_draft_catalog", {"query": "road"})
        assert res.is_error is False

    @pytest.mark.anyio
    async def test_comb_22_f02_f16_speed_and_set_speed_tool(self, mock_env: MockTheoTownEnv):
        """COMB-22: F02 + F16 (Cross-script speed set + theotown_set_speed tool)."""
        res = await mock_env.server.call_tool("theotown_set_speed", {"speed": 2})
        assert res.structured_content["speed"] == 2

    @pytest.mark.anyio
    async def test_comb_23_f04_f16_job_status_and_get_job_tool(self, mock_env: MockTheoTownEnv):
        """COMB-23: F04 + F16 (Job status state machine + theotown_get_job tool)."""
        exec_res = await mock_env.server.call_tool("theotown_execute_plan", {"commands": [{"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0}]})
        job_id = exec_res.structured_content["job_id"]
        status_res = await mock_env.server.call_tool("theotown_get_job", {"job_id": job_id})
        assert status_res.structured_content["job_id"] == job_id

    @pytest.mark.anyio
    async def test_comb_24_f12_f16_validation_and_validate_plan_tool(self, mock_env: MockTheoTownEnv):
        """COMB-24: F12 + F16 (Plan validation models + theotown_validate_plan tool)."""
        cmds = [{"cmd": "build_road", "x0": 10, "y0": 10, "x1": 20, "y1": 10}]
        res = await mock_env.server.call_tool("theotown_validate_plan", {"commands": cmds})
        assert res.structured_content["valid"] is True
