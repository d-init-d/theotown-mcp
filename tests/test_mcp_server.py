"""
Unit tests for MCPServer v2 registration, tools, resources, and prompts in theotown_mcp.server.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theotown_mcp.server import MCPServer


@pytest.mark.anyio
class TestMCPServerRegistration:
    def test_server_metadata(self, mock_server: MCPServer):
        assert mock_server.name == "theotown-mcp"
        assert mock_server.version == "0.1.0"
        assert "TheoTown" in mock_server.instructions

    def test_all_12_tools_registered(self, mock_server: MCPServer):
        registered_tools = list(mock_server._tool_manager._tools.keys())
        expected_tools = [
            "theotown_get_status",
            "theotown_build_road",
            "theotown_build_zone",
            "theotown_build_building",
            "theotown_build_utilities",
            "theotown_demolish",
            "theotown_validate_plan",
            "theotown_execute_plan",
            "theotown_get_job",
            "theotown_cancel_job",
            "theotown_set_speed",
            "theotown_get_draft_catalog",
        ]
        assert len(registered_tools) == 12
        for tool in expected_tools:
            assert tool in registered_tools, f"Missing expected tool {tool}"

    def test_2_resources_registered(self, mock_server: MCPServer):
        resources = list(mock_server._resource_manager._resources.keys())
        assert "theotown://city/status" in resources
        assert "theotown://catalog/drafts" in resources
        assert len(resources) == 2

    def test_1_prompt_registered(self, mock_server: MCPServer):
        prompts = list(mock_server._prompt_manager._prompts.keys())
        assert "urban_planner" in prompts
        assert len(prompts) == 1


@pytest.mark.anyio
class TestMCPServerToolCalls:
    async def test_call_theotown_get_status(self, mock_server: MCPServer, mock_telemetry_file: Path):
        result = await mock_server.call_tool("theotown_get_status", {})
        assert result.is_error is False
        assert result.structured_content["name"] == "EmeraldCity"
        assert result.structured_content["money"] == 75000
        assert result.structured_content["population"] == 1250

    async def test_call_theotown_build_road(self, mock_server: MCPServer):
        args = {"x0": 10, "y0": 10, "x1": 20, "y1": 10, "road_type": "two_lane_road"}
        result = await mock_server.call_tool("theotown_build_road", args)
        assert result.is_error is False
        data = result.structured_content
        assert data["status"] == "enqueued"
        assert data["cmd"] == "build_road"
        assert data["tile_length"] == 11
        assert data["estimated_cost"] == 11 * 50

    async def test_call_theotown_build_zone(self, mock_server: MCPServer):
        args = {"x": 5, "y": 5, "width": 4, "height": 4, "zone_type": "residential_low"}
        result = await mock_server.call_tool("theotown_build_zone", args)
        assert result.is_error is False
        data = result.structured_content
        assert data["status"] == "enqueued"
        assert data["cmd"] == "build_zone"
        assert data["tile_count"] == 16
        assert data["estimated_cost"] == 16 * 10

    async def test_call_theotown_build_building(self, mock_server: MCPServer):
        args = {"x": 20, "y": 20, "building_id": "solar", "rotation": 1}
        result = await mock_server.call_tool("theotown_build_building", args)
        assert result.is_error is False
        data = result.structured_content
        assert data["status"] == "enqueued"
        assert data["building_id"] == "$solarplant00"
        assert data["estimated_cost"] == 8000

    async def test_call_theotown_build_utilities(self, mock_server: MCPServer):
        args = {"x0": 0, "y0": 0, "x1": 10, "y1": 0, "utility_type": "pipe"}
        result = await mock_server.call_tool("theotown_build_utilities", args)
        assert result.is_error is False
        data = result.structured_content
        assert data["status"] == "enqueued"
        assert data["utility_type"] == "pipe"
        assert data["tile_length"] == 11

    async def test_call_theotown_demolish(self, mock_server: MCPServer):
        args = {"x": 10, "y": 10, "width": 2, "height": 3}
        result = await mock_server.call_tool("theotown_demolish", args)
        assert result.is_error is False
        data = result.structured_content
        assert data["status"] == "enqueued"
        assert data["tile_count"] == 6
        assert data["estimated_cost"] == 6 * 5

    async def test_call_theotown_validate_plan(self, mock_server: MCPServer):
        commands = [
            {"cmd": "build_road", "x0": 0, "y0": 0, "x1": 10, "y1": 0},
            {"cmd": "build_zone", "x": 0, "y": 2, "width": 5, "height": 5},
        ]
        result = await mock_server.call_tool("theotown_validate_plan", {"commands": commands, "dry_run": True})
        assert result.is_error is False
        data = result.structured_content
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["command_count"] == 2
        assert data["affected_tiles"] == 11 + 25

    async def test_call_theotown_execute_plan(self, mock_server: MCPServer):
        commands = [
            {"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0},
        ]
        result = await mock_server.call_tool("theotown_execute_plan", {"commands": commands})
        assert result.is_error is False
        data = result.structured_content
        assert data["status"] == "pending"
        assert data["total_steps"] == 1

    async def test_call_theotown_get_and_cancel_job(self, mock_server: MCPServer):
        exec_res = await mock_server.call_tool("theotown_execute_plan", {"commands": [{"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0}]})
        job_id = exec_res.structured_content["job_id"]

        # Get job
        get_res = await mock_server.call_tool("theotown_get_job", {"job_id": job_id})
        assert get_res.is_error is False
        assert get_res.structured_content["job_id"] == job_id
        assert get_res.structured_content["status"] == "pending"

        # Cancel job
        cancel_res = await mock_server.call_tool("theotown_cancel_job", {"job_id": job_id})
        assert cancel_res.is_error is False
        assert cancel_res.structured_content["status"] == "cancelled"

    async def test_call_theotown_set_speed(self, mock_server: MCPServer):
        result = await mock_server.call_tool("theotown_set_speed", {"speed": 3})
        assert result.is_error is False
        assert result.structured_content["speed"] == 3

    async def test_call_theotown_get_draft_catalog(self, mock_server: MCPServer):
        result = await mock_server.call_tool("theotown_get_draft_catalog", {"category": "energy"})
        assert result.is_error is False
        raw_data = result.structured_content
        data = raw_data["result"] if isinstance(raw_data, dict) and "result" in raw_data else raw_data
        assert isinstance(data, list)
        assert len(data) >= 3
        ids = [d["id"] for d in data]
        assert "$solarplant00" in ids


@pytest.mark.anyio
class TestMCPServerResourcesAndPrompts:
    async def test_read_city_status_resource(self, mock_server: MCPServer, mock_telemetry_file: Path):
        contents = await mock_server.read_resource("theotown://city/status")
        assert len(contents) == 1
        assert contents[0].mime_type == "application/json"
        data = json.loads(contents[0].content)
        assert data["name"] == "EmeraldCity"
        assert data["money"] == 75000

    async def test_read_catalog_drafts_resource(self, mock_server: MCPServer):
        contents = await mock_server.read_resource("theotown://catalog/drafts")
        assert len(contents) == 1
        assert contents[0].mime_type == "application/json"
        data = json.loads(contents[0].content)
        assert isinstance(data, list)
        assert len(data) >= 10

    async def test_get_urban_planner_prompt(self, mock_server: MCPServer):
        res = await mock_server.get_prompt("urban_planner", {})
        assert len(res.messages) == 1
        msg = res.messages[0]
        assert msg.role == "user"
        text = msg.content.text
        assert "Road Hierarchy" in text
        assert "Zoning & Pollution" in text
        assert "Utility Coverage" in text
