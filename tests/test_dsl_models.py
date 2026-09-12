"""
Unit tests for Pydantic v2 DSL models, coordinates validation,
and two-layer bounds checking in theotown_mcp.models.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildUtilityCmd,
    BuildZoneCmd,
    CityTelemetry,
    DemolishCmd,
    JobStatus,
    PlanValidationResult,
    parse_command,
    parse_commands,
)


class TestBuildRoadCmd:
    def test_valid_road_default_fields(self):
        cmd = BuildRoadCmd(x0=10, y0=10, x1=25, y1=10)
        assert cmd.cmd == "build_road"
        assert cmd.x0 == 10
        assert cmd.y0 == 10
        assert cmd.x1 == 25
        assert cmd.y1 == 10
        assert cmd.road_type == "$road03"
        assert cmd.level == 0
        assert cmd.tile_length == 16

    def test_tile_length_calculation(self):
        # Single tile
        assert BuildRoadCmd(x0=5, y0=5, x1=5, y1=5).tile_length == 1
        # Horizontal road
        assert BuildRoadCmd(x0=0, y0=10, x1=20, y1=10).tile_length == 21
        # Vertical road
        assert BuildRoadCmd(x0=10, y0=0, x1=10, y1=30).tile_length == 31
        # Manhattan L-shape
        assert BuildRoadCmd(x0=0, y0=0, x1=10, y1=20).tile_length == 31

    def test_elevation_level_bounds(self):
        # Minimum elevation -2 (tunnel)
        cmd_tunnel = BuildRoadCmd(x0=0, y0=0, x1=5, y1=0, level=-2)
        assert cmd_tunnel.level == -2
        # Maximum elevation 2 (bridge)
        cmd_bridge = BuildRoadCmd(x0=0, y0=0, x1=5, y1=0, level=2)
        assert cmd_bridge.level == 2

        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=0, level=-3)

        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=0, level=3)

    def test_negative_coordinates_rejected(self):
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=-1, y0=0, x1=5, y1=0)
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=0, y0=-5, x1=5, y1=0)
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=0, y0=0, x1=-2, y1=0)
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=-10)

    def test_empty_road_type_rejected(self):
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=0, road_type="")

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=0, unexpected="field")

    def test_check_bounds(self):
        cmd = BuildRoadCmd(x0=10, y0=10, x1=50, y1=10)
        # Inside 128x128 map
        assert cmd.check_bounds(128, 128) == []

        # Outside width
        cmd_out_x = BuildRoadCmd(x0=10, y0=10, x1=130, y1=10)
        errs_x = cmd_out_x.check_bounds(128, 128)
        assert len(errs_x) == 1
        assert "width: 128" in errs_x[0]

        # Outside height
        cmd_out_y = BuildRoadCmd(x0=10, y0=10, x1=10, y1=150)
        errs_y = cmd_out_y.check_bounds(128, 128)
        assert len(errs_y) == 1
        assert "height: 128" in errs_y[0]


class TestBuildZoneCmd:
    def test_valid_zone_default_fields(self):
        cmd = BuildZoneCmd(x=10, y=10)
        assert cmd.cmd == "build_zone"
        assert cmd.x == 10
        assert cmd.y == 10
        assert cmd.width == 1
        assert cmd.height == 1
        assert cmd.zone_type == "residential_low"
        assert cmd.tile_count == 1

    def test_tile_count_calculation(self):
        cmd = BuildZoneCmd(x=5, y=5, width=4, height=6, zone_type="commercial_high")
        assert cmd.tile_count == 24

    def test_negative_origin_rejected(self):
        with pytest.raises(ValidationError):
            BuildZoneCmd(x=-1, y=5)
        with pytest.raises(ValidationError):
            BuildZoneCmd(x=5, y=-2)

    def test_zero_or_negative_dimensions_rejected(self):
        with pytest.raises(ValidationError):
            BuildZoneCmd(x=0, y=0, width=0, height=1)
        with pytest.raises(ValidationError):
            BuildZoneCmd(x=0, y=0, width=1, height=0)
        with pytest.raises(ValidationError):
            BuildZoneCmd(x=0, y=0, width=-3, height=4)

    def test_check_bounds(self):
        # Inside boundary
        cmd = BuildZoneCmd(x=120, y=120, width=8, height=8)
        assert cmd.check_bounds(128, 128) == []

        # Exceeds width
        cmd_over_w = BuildZoneCmd(x=125, y=50, width=5, height=2)
        errs_w = cmd_over_w.check_bounds(128, 128)
        assert len(errs_w) == 1
        assert "exceeds city width (128)" in errs_w[0]

        # Exceeds height
        cmd_over_h = BuildZoneCmd(x=50, y=125, width=2, height=5)
        errs_h = cmd_over_h.check_bounds(128, 128)
        assert len(errs_h) == 1
        assert "exceeds city height (128)" in errs_h[0]


class TestBuildBuildingCmd:
    def test_valid_building_default_fields(self):
        cmd = BuildBuildingCmd(x=15, y=20, building_id="$park00")
        assert cmd.cmd == "build_building"
        assert cmd.x == 15
        assert cmd.y == 20
        assert cmd.building_id == "$park00"
        assert cmd.rotation == 0

    def test_rotation_values(self):
        for rot in (0, 1, 2, 3):
            assert BuildBuildingCmd(x=0, y=0, building_id="test", rotation=rot).rotation == rot

        with pytest.raises(ValidationError):
            BuildBuildingCmd(x=0, y=0, building_id="test", rotation=4)
        with pytest.raises(ValidationError):
            BuildBuildingCmd(x=0, y=0, building_id="test", rotation=-1)

    def test_empty_building_id_rejected(self):
        with pytest.raises(ValidationError):
            BuildBuildingCmd(x=0, y=0, building_id="")

    def test_negative_coordinates_rejected(self):
        with pytest.raises(ValidationError):
            BuildBuildingCmd(x=-5, y=0, building_id="$park00")
        with pytest.raises(ValidationError):
            BuildBuildingCmd(x=0, y=-1, building_id="$park00")

    def test_check_bounds_with_footprint(self):
        cmd = BuildBuildingCmd(x=126, y=126, building_id="$hospital00")
        # 1x1 footprint fits
        assert cmd.check_bounds(128, 128, footprint_w=1, footprint_h=1) == []
        # 2x2 footprint fits
        assert cmd.check_bounds(128, 128, footprint_w=2, footprint_h=2) == []
        # 3x3 footprint exceeds map edge
        errs = cmd.check_bounds(128, 128, footprint_w=3, footprint_h=3)
        assert len(errs) == 2


class TestBuildUtilityCmd:
    def test_valid_pipe_and_wire(self):
        pipe_cmd = BuildUtilityCmd(x0=10, y0=10, x1=20, y1=10, utility_type="pipe")
        assert pipe_cmd.cmd == "build_utility"
        assert pipe_cmd.utility_type == "pipe"
        assert pipe_cmd.tile_length == 11

        wire_cmd = BuildUtilityCmd(x0=10, y0=10, x1=10, y1=25, utility_type="wire")
        assert wire_cmd.utility_type == "wire"
        assert wire_cmd.tile_length == 16

    def test_invalid_utility_type_rejected(self):
        with pytest.raises(ValidationError):
            BuildUtilityCmd(x0=0, y0=0, x1=5, y1=0, utility_type="fiber_optic")

    def test_negative_coordinates_rejected(self):
        with pytest.raises(ValidationError):
            BuildUtilityCmd(x0=-1, y0=0, x1=5, y1=0)

    def test_check_bounds(self):
        cmd = BuildUtilityCmd(x0=0, y0=0, x1=127, y1=0)
        assert cmd.check_bounds(128, 128) == []

        cmd_out = BuildUtilityCmd(x0=0, y0=0, x1=130, y1=0)
        errs = cmd_out.check_bounds(128, 128)
        assert len(errs) == 1


class TestDemolishCmd:
    def test_valid_demolish(self):
        cmd = DemolishCmd(x=5, y=5, width=3, height=3)
        assert cmd.cmd == "demolish"
        assert cmd.tile_count == 9

    def test_zero_or_negative_dimensions_rejected(self):
        with pytest.raises(ValidationError):
            DemolishCmd(x=0, y=0, width=0, height=1)
        with pytest.raises(ValidationError):
            DemolishCmd(x=0, y=0, width=1, height=-2)

    def test_negative_origin_rejected(self):
        with pytest.raises(ValidationError):
            DemolishCmd(x=-1, y=0)

    def test_check_bounds(self):
        cmd = DemolishCmd(x=120, y=120, width=8, height=8)
        assert cmd.check_bounds(128, 128) == []

        cmd_out = DemolishCmd(x=125, y=125, width=5, height=5)
        errs = cmd_out.check_bounds(128, 128)
        assert len(errs) == 2


class TestDiscriminatedUnionAndParsing:
    def test_parse_command_individual(self):
        road = parse_command({"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0})
        assert isinstance(road, BuildRoadCmd)

        zone = parse_command({"cmd": "build_zone", "x": 0, "y": 0, "width": 2, "height": 2})
        assert isinstance(zone, BuildZoneCmd)

        building = parse_command({"cmd": "build_building", "x": 10, "y": 10, "building_id": "$park00"})
        assert isinstance(building, BuildBuildingCmd)

        util = parse_command({"cmd": "build_utility", "x0": 0, "y0": 0, "x1": 10, "y1": 0})
        assert isinstance(util, BuildUtilityCmd)

        demolish = parse_command({"cmd": "demolish", "x": 0, "y": 0, "width": 1, "height": 1})
        assert isinstance(demolish, DemolishCmd)

    def test_parse_command_identity_for_instances(self):
        cmd = BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)
        assert parse_command(cmd) is cmd

    def test_parse_command_unknown_discriminator_rejected(self):
        with pytest.raises(ValidationError):
            parse_command({"cmd": "launch_spaceship", "x": 0, "y": 0})

    def test_parse_commands_polymorphic_list(self):
        raw_list = [
            {"cmd": "build_road", "x0": 10, "y0": 10, "x1": 20, "y1": 10},
            {"cmd": "build_zone", "x": 10, "y": 12, "width": 4, "height": 4, "zone_type": "residential_low"},
            {"cmd": "build_building", "x": 20, "y": 20, "building_id": "$watertower00"},
            {"cmd": "build_utility", "x0": 10, "y0": 10, "x1": 20, "y1": 10, "utility_type": "pipe"},
            {"cmd": "demolish", "x": 30, "y": 30, "width": 2, "height": 2},
        ]
        parsed = parse_commands(raw_list)
        assert len(parsed) == 5
        assert isinstance(parsed[0], BuildRoadCmd)
        assert isinstance(parsed[1], BuildZoneCmd)
        assert isinstance(parsed[2], BuildBuildingCmd)
        assert isinstance(parsed[3], BuildUtilityCmd)
        assert isinstance(parsed[4], DemolishCmd)


class TestPlanValidationResultAndJobStatus:
    def test_plan_validation_result(self):
        res = PlanValidationResult(valid=True, estimated_cost=1500, command_count=3, affected_tiles=25)
        assert res.valid is True
        assert res.estimated_cost == 1500
        assert res.command_count == 3
        assert res.affected_tiles == 25
        assert res.errors == []
        assert res.warnings == []

    def test_job_status_states(self):
        for st in ("pending", "running", "completed", "failed", "cancelled"):
            js = JobStatus(
                job_id="job_123",
                status=st,
                progress=0.5,
                total_steps=10,
                completed_steps=5,
                created_at=100.0,
                updated_at=105.0,
            )
            assert js.status == st

        with pytest.raises(ValidationError):
            JobStatus(
                job_id="job_123",
                status="paused",
                created_at=100.0,
                updated_at=105.0,
            )


class TestCityTelemetryModel:
    def test_city_telemetry_defaults_and_custom(self):
        telem = CityTelemetry()
        assert telem.name == "Unknown"
        assert telem.money == 0
        assert telem.population == 0
        assert telem.happiness == 100.0
        assert telem.width == 128
        assert telem.height == 128
        assert telem.speed == 1
        assert telem.connected is True

        custom = CityTelemetry(
            name="MegaCity",
            money=1000000,
            population=50000,
            happiness=95.5,
            width=256,
            height=256,
            year=2030,
            month=6,
            day=15,
            speed=3,
        )
        assert custom.name == "MegaCity"
        assert custom.money == 1000000
        assert custom.speed == 3

    def test_city_telemetry_speed_literal_bounds(self):
        for s in (0, 1, 2, 3, 4):
            assert CityTelemetry(speed=s).speed == s

        with pytest.raises(ValidationError):
            CityTelemetry(speed=5)
