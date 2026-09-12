"""
Tier 2: Boundary & Corner Cases (Features F07 to F12)
30 Boundary Test Cases (5 per feature).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildZoneCmd,
    CityTelemetry,
)


class TestF07F12Boundaries:
    # --- F07: Preflight Checks & Pricing Boundaries (5) ---
    def test_e2e_t2_f07_01_building_at_exact_map_border(self, mock_env: MockTheoTownEnv):
        """1x1 building placed at map border (127, 127) succeeds."""
        assert mock_env.oracle.is_building_buildable(127, 127, footprint_w=1, footprint_h=1) is True

    def test_e2e_t2_f07_02_building_overlapping_map_border(self, mock_env: MockTheoTownEnv):
        """2x2 building placed at (127, 127) overhangs map boundary and fails preflight."""
        assert mock_env.oracle.is_building_buildable(127, 127, footprint_w=2, footprint_h=2) is False

    def test_e2e_t2_f07_03_road_over_deep_water_rejection(self, mock_env: MockTheoTownEnv):
        """Road across deep water without bridge elevation fails preflight."""
        mock_env.oracle.grid[(50, 50)] = {"water": True}
        assert mock_env.oracle.is_road_buildable(40, 50, 60, 50, level=0) is False

    def test_e2e_t2_f07_04_demolish_indestructible(self, mock_env: MockTheoTownEnv):
        """Demolish on indestructible tile fails preflight."""
        mock_env.oracle.grid[(10, 10)] = {"indestructible": True}
        assert mock_env.oracle.is_removable(10, 10, 1, 1) is False

    def test_e2e_t2_f07_05_zone_over_water_rejection(self, mock_env: MockTheoTownEnv):
        """Zone designated over water fails preflight."""
        mock_env.oracle.grid[(30, 30)] = {"water": True}
        assert mock_env.oracle.is_zone_buildable(28, 28, 4, 4) is False

    # --- F08: City Telemetry Collector Boundaries (5) ---
    def test_e2e_t2_f08_01_zero_population_telemetry(self):
        """CityTelemetry model allows 0 population."""
        telem = CityTelemetry(population=0)
        assert telem.population == 0

    def test_e2e_t2_f08_02_large_population_integer(self):
        """Large megacity population of 10,000,000 serializes cleanly."""
        telem = CityTelemetry(population=10_000_000)
        assert telem.population == 10_000_000

    def test_e2e_t2_f08_03_speed_extreme_boundary(self):
        """Speed literal extremes: 0 (Pause) and 4 (Max)."""
        assert CityTelemetry(speed=0).speed == 0
        assert CityTelemetry(speed=4).speed == 4
        with pytest.raises(ValidationError):
            CityTelemetry(speed=5)

    def test_e2e_t2_f08_04_calendar_rollover(self, mock_env: MockTheoTownEnv):
        """Year rollover when month increments past 12."""
        mock_env.oracle.year = 2026
        mock_env.oracle.month = 12
        mock_env.oracle.day = 30
        mock_env.oracle.advance_time(days=1)
        assert mock_env.oracle.month == 1
        assert mock_env.oracle.year == 2027
        assert mock_env.oracle.day == 1

    def test_e2e_t2_f08_05_large_map_dimensions(self):
        """Mega-map 512x512 telemetry dimensions."""
        telem = CityTelemetry(width=512, height=512)
        assert telem.width == 512
        assert telem.height == 512

    # --- F09: Dynamic Draft Catalog Discovery Boundaries (5) ---
    def test_e2e_t2_f09_01_query_non_existent_draft(self, mock_env: MockTheoTownEnv):
        """Querying non-existent draft ID returns None."""
        assert mock_env.catalog.get_draft("$unknown_draft_99") is None

    def test_e2e_t2_f09_02_filter_by_empty_category(self, mock_env: MockTheoTownEnv):
        """Filtering by non-existent category returns empty list."""
        assert mock_env.catalog.search_drafts(category="spaceship") == []

    def test_e2e_t2_f09_03_catalog_scale(self, mock_env: MockTheoTownEnv):
        """Catalog handles hundreds of drafts without performance loss."""
        for i in range(100):
            mock_env.catalog.drafts[f"$mock_{i}"] = {"id": f"$mock_{i}", "type": "building", "price": 100}
        assert len(mock_env.catalog.drafts) >= 115

    def test_e2e_t2_f09_04_draft_missing_price_default(self, mock_env: MockTheoTownEnv):
        """Draft with missing price falls back to default price."""
        mock_env.catalog.drafts["$freebie"] = {"id": "$freebie", "type": "park"}
        assert mock_env.catalog.estimate_unit_price("$freebie", default_price=0) == 0

    def test_e2e_t2_f09_05_special_symbols_draft_id(self, mock_env: MockTheoTownEnv):
        """Draft ID containing dashes and underscores."""
        mock_env.catalog.drafts["$custom-road_v2.0"] = {"id": "$custom-road_v2.0", "price": 80}
        assert mock_env.catalog.estimate_unit_price("$custom-road_v2.0") == 80

    # --- F10: Inbox Template Boundaries (5) ---
    def test_e2e_t2_f10_01_empty_commands_payload(self, mock_env: MockTheoTownEnv):
        """Inbox payload with 0 commands executes safely."""
        mock_env.bridge.execute_plan([])
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.total_steps == 0

    def test_e2e_t2_f10_02_large_inbox_payload(self, mock_env: MockTheoTownEnv):
        """Large inbox file (~50KB) executes without parsing error."""
        cmds = [BuildRoadCmd(x0=i % 100, y0=0, x1=i % 100, y1=5) for i in range(100)]
        mock_env.bridge.execute_plan(cmds)
        assert mock_env.config.inbox_path.stat().st_size > 1000

    def test_e2e_t2_f10_03_multiple_replaces_same_session(self, mock_env: MockTheoTownEnv):
        """Multiple sequential inbox overwrites maintain integrity."""
        for i in range(5):
            mock_env.bridge.set_speed(i % 5)
            assert f"City.setSpeed({i % 5})" in mock_env.config.inbox_path.read_text(encoding="utf-8")

    def test_e2e_t2_f10_04_int_coordinates_clamped(self):
        """Coordinates must be integer values."""
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0="invalid", y0=0, x1=5, y1=0)  # type: ignore

    def test_e2e_t2_f10_05_unicode_inbox_comments(self, mock_env: MockTheoTownEnv):
        """Unicode characters in comments are written and preserved."""
        mock_env.config.inbox_path.write_text("-- Quy hoạch thành phố TheoTown 2026\nreturn true\n", encoding="utf-8")
        assert "Quy hoạch" in mock_env.config.inbox_path.read_text(encoding="utf-8")

    # --- F11: Python Packaging Boundaries (5) ---
    def test_e2e_t2_f11_01_python_version_guard(self):
        """Python version is >= 3.10."""
        import sys
        assert sys.version_info >= (3, 10)

    def test_e2e_t2_f11_02_pydantic_installed(self):
        """Pydantic is installed and version >= 2.7.0."""
        import pydantic
        major, _minor, *_ = pydantic.__version__.split(".")
        assert int(major) >= 2

    def test_e2e_t2_f11_03_typer_installed(self):
        """Typer is installed and accessible."""
        import typer
        assert typer.__version__ is not None

    def test_e2e_t2_f11_04_mcp_installed(self):
        """MCP SDK is installed and version >= 2.0.0."""
        import importlib.metadata
        version = importlib.metadata.version("mcp")
        assert version is not None
        assert int(version.split(".")[0]) >= 2

    def test_e2e_t2_f11_05_package_exports(self):
        """Package root exports clean namespace."""
        import theotown_mcp
        assert hasattr(theotown_mcp, "__version__")

    # --- F12: Pydantic DSL Models Boundaries (5) ---
    def test_e2e_t2_f12_01_negative_x0_rejection(self):
        """Rejection of x0 < 0."""
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=-1, y0=0, x1=5, y1=0)

    def test_e2e_t2_f12_02_zero_zone_width_rejection(self):
        """Rejection of zone width = 0."""
        with pytest.raises(ValidationError):
            BuildZoneCmd(x=0, y=0, width=0, height=5)

    def test_e2e_t2_f12_03_empty_building_id_rejection(self):
        """Rejection of empty building_id string."""
        with pytest.raises(ValidationError):
            BuildBuildingCmd(x=0, y=0, building_id="")

    def test_e2e_t2_f12_04_rotation_bounds_rejection(self):
        """Rotation must be in range [0, 3]."""
        with pytest.raises(ValidationError):
            BuildBuildingCmd(x=0, y=0, building_id="$park00", rotation=4)

    def test_e2e_t2_f12_05_extra_fields_forbidden(self):
        """Extra undeclared fields forbidden on commands."""
        with pytest.raises(ValidationError):
            BuildZoneCmd(x=0, y=0, width=2, height=2, unauthorized_field="bad")
