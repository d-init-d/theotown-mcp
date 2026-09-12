"""
Tier 1: Feature F07 — Preflight Checks & Pricing
5 Isolated Test Cases.
"""

from __future__ import annotations

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.models import BuildBuildingCmd, BuildRoadCmd


class TestFeatureF07PreflightPricing:
    def test_e2e_t1_f07_01_valid_road_preflight(self, mock_env: MockTheoTownEnv):
        """Preflight succeeds on unobstructed empty terrain."""
        assert mock_env.oracle.is_road_buildable(20, 20, 30, 20) is True

    def test_e2e_t1_f07_02_blocked_road_preflight(self, mock_env: MockTheoTownEnv):
        """Preflight fails on water obstacle without bridge elevation."""
        mock_env.oracle.grid[(25, 20)] = {"water": True}
        assert mock_env.oracle.is_road_buildable(20, 20, 30, 20, level=0) is False

    def test_e2e_t1_f07_03_accurate_price_query(self, mock_env: MockTheoTownEnv):
        """Builder road pricing estimates accurately."""
        cmd = BuildRoadCmd(x0=0, y0=0, x1=9, y1=0, road_type="$road03")
        price = mock_env.catalog.estimate_command_cost(cmd)
        assert price == 10 * 50

    def test_e2e_t1_f07_04_building_buildability(self, mock_env: MockTheoTownEnv):
        """Preflight check on building footprint."""
        assert mock_env.oracle.is_building_buildable(10, 10, footprint_w=2, footprint_h=2) is True
        mock_env.oracle.grid[(11, 11)] = {"building": "$existing"}
        assert mock_env.oracle.is_building_buildable(10, 10, footprint_w=2, footprint_h=2) is False

    def test_e2e_t1_f07_05_insufficient_funds_rejection(self, mock_env: MockTheoTownEnv):
        """Preflight check rejects execution when funds are insufficient."""
        mock_env.oracle.money = 100
        cmd = BuildBuildingCmd(x=5, y=5, building_id="$solarplant00")
        res = mock_env.oracle.execute_command(cmd)
        assert res["success"] is False
        assert "Insufficient funds" in res["error"]
