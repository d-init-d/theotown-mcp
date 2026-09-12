"""
TheoTown MCP Server: Model Context Protocol (MCP) server for TheoTown city simulation.
Enables AI reasoning agents to inspect, plan, and autonomously construct cities in TheoTown.
"""

from theotown_mcp.bridge import (
    TheoTownBridge,
    generate_job_lua,
    get_bridge,
    serialize_to_lua,
    write_atomic_lua,
)
from theotown_mcp.catalog import (
    DraftCatalog,
    get_catalog,
)
from theotown_mcp.cli import (
    app,
)
from theotown_mcp.config import (
    TheoTownConfig,
    get_config,
)
from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildUtilityCmd,
    BuildZoneCmd,
    CityCommand,
    CityTelemetry,
    DemolishCmd,
    JobStatus,
    PlanCommand,
    PlanValidationResult,
    parse_command,
    parse_commands,
)
from theotown_mcp.server import (
    create_server,
    server,
)

__version__ = "0.1.0"

__all__ = [
    "BuildBuildingCmd",
    "BuildRoadCmd",
    "BuildUtilityCmd",
    "BuildZoneCmd",
    "CityCommand",
    "CityTelemetry",
    "DemolishCmd",
    "DraftCatalog",
    "JobStatus",
    "PlanCommand",
    "PlanValidationResult",
    "TheoTownBridge",
    "TheoTownConfig",
    "__version__",
    "app",
    "create_server",
    "generate_job_lua",
    "get_bridge",
    "get_catalog",
    "get_config",
    "parse_command",
    "parse_commands",
    "serialize_to_lua",
    "server",
    "write_atomic_lua",
]
