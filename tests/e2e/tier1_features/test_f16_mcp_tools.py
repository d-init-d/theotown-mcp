"""
Tier 1: Feature F16 — MCP Server v2 Tools
5 Isolated Test Cases.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import MockTheoTownEnv


@pytest.mark.anyio
class TestFeatureF16MCPTools:
    async def test_e2e_t1_f16_01_tool_get_status(self, mock_env: MockTheoTownEnv):
        """Invoke tool theotown_get_status via MCP server."""
        res = await mock_env.server.call_tool("theotown_get_status", {})
        assert res.is_error is False
        assert res.structured_content["name"] == "E2ETestCity"

    async def test_e2e_t1_f16_02_tool_build_road(self, mock_env: MockTheoTownEnv):
        """Invoke tool theotown_build_road."""
        args = {"x0": 10, "y0": 10, "x1": 20, "y1": 10}
        res = await mock_env.server.call_tool("theotown_build_road", args)
        assert res.is_error is False
        assert res.structured_content["status"] == "enqueued"

    async def test_e2e_t1_f16_03_tool_build_zone(self, mock_env: MockTheoTownEnv):
        """Invoke tool theotown_build_zone."""
        args = {"x": 5, "y": 5, "width": 3, "height": 3, "zone_type": "residential_low"}
        res = await mock_env.server.call_tool("theotown_build_zone", args)
        assert res.is_error is False
        assert res.structured_content["tile_count"] == 9

    async def test_e2e_t1_f16_04_tool_validate_plan(self, mock_env: MockTheoTownEnv):
        """Invoke tool theotown_validate_plan."""
        cmds = [{"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0}]
        res = await mock_env.server.call_tool("theotown_validate_plan", {"commands": cmds})
        assert res.is_error is False
        assert res.structured_content["valid"] is True

    async def test_e2e_t1_f16_05_tool_set_speed(self, mock_env: MockTheoTownEnv):
        """Invoke tool theotown_set_speed."""
        res = await mock_env.server.call_tool("theotown_set_speed", {"speed": 2})
        assert res.is_error is False
        assert res.structured_content["speed"] == 2
