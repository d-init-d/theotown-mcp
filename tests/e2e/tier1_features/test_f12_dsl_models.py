"""
Tier 1: Feature F12 — Pydantic v2 DSL Models
5 Isolated Test Cases.
"""

from __future__ import annotations

from theotown_mcp.bridge import serialize_to_lua
from theotown_mcp.models import (
    BuildRoadCmd,
    BuildZoneCmd,
    DemolishCmd,
    parse_commands,
)


class TestFeatureF12DSLModels:
    def test_e2e_t1_f12_01_valid_build_road(self):
        """Instantiate valid BuildRoadCmd and compute length."""
        cmd = BuildRoadCmd(x0=10, y0=10, x1=20, y1=10, road_type="$road03")
        assert cmd.cmd == "build_road"
        assert cmd.tile_length == 11

    def test_e2e_t1_f12_02_valid_build_zone(self):
        """Instantiate valid BuildZoneCmd and compute tile count."""
        cmd = BuildZoneCmd(x=5, y=5, width=4, height=4, zone_type="residential_low")
        assert cmd.cmd == "build_zone"
        assert cmd.tile_count == 16

    def test_e2e_t1_f12_03_discriminated_union_parsing(self):
        """Polymorphic list deserialization via discriminator."""
        raw = [
            {"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0},
            {"cmd": "demolish", "x": 2, "y": 2},
        ]
        parsed = parse_commands(raw)
        assert len(parsed) == 2
        assert isinstance(parsed[0], BuildRoadCmd)
        assert isinstance(parsed[1], DemolishCmd)

    def test_e2e_t1_f12_04_runtime_bounds_checking(self):
        """Runtime boundary checking against city dimensions."""
        cmd = BuildRoadCmd(x0=10, y0=10, x1=50, y1=10)
        assert cmd.check_bounds(city_width=128, city_height=128) == []

        cmd_out = BuildRoadCmd(x0=10, y0=10, x1=150, y1=10)
        assert len(cmd_out.check_bounds(city_width=128, city_height=128)) == 1

    def test_e2e_t1_f12_05_serialize_to_lua(self):
        """Model serialization to clean Lua dictionary representation."""
        cmd = BuildRoadCmd(x0=0, y0=0, x1=10, y1=0)
        lua_str = serialize_to_lua(cmd)
        assert 'cmd = "build_road"' in lua_str
        assert "x0 = 0" in lua_str
        assert "x1 = 10" in lua_str
