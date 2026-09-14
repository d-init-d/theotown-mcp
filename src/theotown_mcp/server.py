"""
Model Context Protocol (MCP) Server v2 implementation for TheoTown.
Built on `mcp>=2.0.0,<3.0.0` using `MCPServer` from `mcp.server`.
Exposes 12 Tools, 2 Resources, and 1 Prompt across stdio and streamable-http transports.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server import MCPServer

from theotown_mcp.bridge import TheoTownBridge, get_bridge
from theotown_mcp.catalog import DraftCatalog, get_catalog
from theotown_mcp.config import TheoTownConfig, get_config
from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildUtilityCmd,
    BuildZoneCmd,
    CityTelemetry,
    DemolishCmd,
    JobStatus,
    PlanValidationResult,
)

SERVER_INSTRUCTIONS = (
    "You are connected to a live TheoTown city simulation via theotown-mcp. "
    "Follow these operational guidelines:\n"
    "1. Always check city status with `theotown_get_status` or the `theotown://city/status` resource "
    "before undertaking major infrastructure or zoning works.\n"
    "2. Use `theotown_validate_plan` to dry-run construction layouts, verify grid boundaries, "
    "and check treasury costs before committing builds.\n"
    "3. Roads, zones, utilities, and buildings can be constructed with dedicated tools or batched via `theotown_execute_plan`.\n"
    "4. For long-running batch jobs, monitor progress via `theotown_get_job`.\n"
    "5. Use `theotown_get_draft_catalog` to explore available building types, roads, and utilities."
)

URBAN_PLANNER_PROMPT = (
    "You are an expert Urban Planner and Civil Engineer governing a TheoTown city.\n\n"
    "Core Principles:\n"
    "1. **Road Hierarchy**: Structure the transit network with high-capacity avenues/highways connecting "
    "to collector roads, branching into local two-lane residential and commercial streets. Avoid dead ends.\n"
    "2. **Zoning & Pollution Management**: Separate heavy industrial zones from residential neighborhoods "
    "using green belts (parks) or commercial zones to avoid pollution-induced sickness and population loss.\n"
    "3. **Utility Coverage**: Guarantee complete water (pipes & water towers) and power (turbines/solar/coal & wires) "
    "connectivity before inviting residents to settle in new zones.\n"
    "4. **Budget Discipline**: Monitor treasury reserves. Never spend below a safe emergency threshold (~2,000 Theons). "
    "Always validate plans first using `theotown_validate_plan`.\n"
    "5. **Expansion Rhythm**: Expand in modular neighborhood blocks (e.g. 8x8 or 16x16 grids), balancing RCI demand."
)


def create_server(
    config: TheoTownConfig | None = None,
    bridge: TheoTownBridge | None = None,
    catalog: DraftCatalog | None = None,
) -> MCPServer:
    """Creates and configures an MCPServer v2 instance exposing TheoTown endpoints."""
    cfg = config or get_config()
    cat = catalog or get_catalog(cfg)
    br = bridge or get_bridge(cfg)

    server = MCPServer(
        name="theotown-mcp",
        version="0.2.0",
        description="TheoTown MCP Server: AI Autonomous Urban Planning and Construction Engine",
        instructions=SERVER_INSTRUCTIONS,
    )

    # -------------------------------------------------------------------------
    # 12 MCP Tools
    # -------------------------------------------------------------------------

    @server.tool(name="theotown_get_status", description="Retrieve active TheoTown city status, economy, population, dimensions, and simulation speed.")
    def theotown_get_status() -> CityTelemetry:
        return br.read_telemetry()

    @server.tool(name="theotown_build_road", description="Construct a road segment between (x0, y0) and (x1, y1).")
    def theotown_build_road(
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        road_type: str = "$road00",
        level: int = 0,
    ) -> dict[str, Any]:
        resolved_type = cat.resolve_draft_id(road_type)
        cmd = BuildRoadCmd(x0=x0, y0=y0, x1=x1, y1=y1, road_type=resolved_type, level=level)
        job = br.execute_plan([cmd])
        cost = cat.estimate_command_cost(cmd)
        return {
            "status": "enqueued",
            "job_id": job.job_id,
            "cmd": "build_road",
            "road_type": resolved_type,
            "tile_length": cmd.tile_length,
            "estimated_cost": cost,
        }

    @server.tool(name="theotown_build_zone", description="Designate zoning over a rectangular area starting at (x, y) with width and height.")
    def theotown_build_zone(
        x: int,
        y: int,
        width: int = 1,
        height: int = 1,
        zone_type: str = "residential_low",
    ) -> dict[str, Any]:
        resolved_type = cat.resolve_draft_id(zone_type)
        cmd = BuildZoneCmd(x=x, y=y, width=width, height=height, zone_type=resolved_type)
        job = br.execute_plan([cmd])
        cost = cat.estimate_command_cost(cmd)
        return {
            "status": "enqueued",
            "job_id": job.job_id,
            "cmd": "build_zone",
            "tile_count": cmd.tile_count,
            "estimated_cost": cost,
        }

    @server.tool(name="theotown_build_building", description="Place a building draft at (x, y) with optional rotation (0-3).")
    def theotown_build_building(
        x: int,
        y: int,
        building_id: str,
        rotation: int = 0,
    ) -> dict[str, Any]:
        resolved_id = cat.resolve_draft_id(building_id)
        cmd = BuildBuildingCmd(x=x, y=y, building_id=resolved_id, rotation=rotation)
        job = br.execute_plan([cmd])
        cost = cat.estimate_command_cost(cmd)
        return {
            "status": "enqueued",
            "job_id": job.job_id,
            "cmd": "build_building",
            "building_id": resolved_id,
            "estimated_cost": cost,
        }

    @server.tool(name="theotown_build_utilities", description="Lay underground pipes or power wires between (x0, y0) and (x1, y1).")
    def theotown_build_utilities(
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        utility_type: Literal["pipe", "wire"] = "pipe",
    ) -> dict[str, Any]:
        cmd = BuildUtilityCmd(x0=x0, y0=y0, x1=x1, y1=y1, utility_type=utility_type)
        job = br.execute_plan([cmd])
        cost = cat.estimate_command_cost(cmd)
        return {
            "status": "enqueued",
            "job_id": job.job_id,
            "cmd": "build_utility",
            "utility_type": utility_type,
            "tile_length": cmd.tile_length,
            "estimated_cost": cost,
        }

    @server.tool(name="theotown_demolish", description="Demolish buildings, roads, or zones within a rectangular area starting at (x, y).")
    def theotown_demolish(
        x: int,
        y: int,
        width: int = 1,
        height: int = 1,
    ) -> dict[str, Any]:
        cmd = DemolishCmd(x=x, y=y, width=width, height=height)
        job = br.execute_plan([cmd])
        cost = cat.estimate_command_cost(cmd)
        return {
            "status": "enqueued",
            "job_id": job.job_id,
            "cmd": "demolish",
            "tile_count": cmd.tile_count,
            "estimated_cost": cost,
        }

    @server.tool(name="theotown_validate_plan", description="Perform dry-run bounds checks and cost estimations for a batch of construction commands.")
    def theotown_validate_plan(
        commands: list[dict[str, Any]],
        dry_run: bool = True,
    ) -> PlanValidationResult:
        return br.validate_plan(commands, dry_run=dry_run)

    @server.tool(name="theotown_execute_plan", description="Submit a batch construction plan to the in-game execution queue.")
    def theotown_execute_plan(
        commands: list[dict[str, Any]],
    ) -> JobStatus:
        return br.execute_plan(commands)

    @server.tool(name="theotown_get_job", description="Query progress and execution status of a submitted construction job.")
    def theotown_get_job(
        job_id: str,
    ) -> JobStatus:
        return br.get_job_status(job_id)

    @server.tool(name="theotown_cancel_job", description="Cancel a pending construction job.")
    def theotown_cancel_job(
        job_id: str,
    ) -> dict[str, Any]:
        return br.cancel_job(job_id)

    @server.tool(name="theotown_set_speed", description="Set game simulation speed: 0 (Pause), 1 (Normal), 2 (Fast), 3 (Ultra), 4 (Max).")
    def theotown_set_speed(
        speed: Literal[0, 1, 2, 3, 4],
    ) -> dict[str, Any]:
        return br.set_speed(speed)

    @server.tool(name="theotown_get_draft_catalog", description="Search and list available drafts, buildings, roads, and utilities.")
    def theotown_get_draft_catalog(
        category: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        return cat.search_drafts(category=category, query=query)

    # -------------------------------------------------------------------------
    # 2 MCP Resources
    # -------------------------------------------------------------------------

    @server.resource("theotown://city/status", mime_type="application/json")
    def get_city_status_resource() -> str:
        """Live dump of active city telemetry."""
        status = br.read_telemetry()
        return status.model_dump_json(indent=2)

    @server.resource("theotown://catalog/drafts", mime_type="application/json")
    def get_catalog_drafts_resource() -> str:
        """Dump of available drafts and aliases."""
        return json.dumps(list(cat.drafts.values()), indent=2)

    # -------------------------------------------------------------------------
    # 1 MCP Prompt
    # -------------------------------------------------------------------------

    @server.prompt("urban_planner")
    def get_urban_planner_prompt() -> str:
        """Prompt template guiding LLMs in sustainable city planning and construction."""
        return URBAN_PLANNER_PROMPT

    return server


_default_server: MCPServer | None = None


def get_default_server() -> MCPServer:
    """Returns or initializes the default MCPServer instance."""
    global _default_server
    if _default_server is None:
        _default_server = create_server()
    return _default_server


def reset_server() -> None:
    """Resets the default MCPServer instance for clean test isolation."""
    global _default_server
    _default_server = None


def __getattr__(name: str) -> Any:
    if name == "server":
        return get_default_server()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
