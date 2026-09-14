"""
Domain-Specific Language (DSL) models for TheoTown MCP Server.
Provides strict Pydantic v2 command models, discriminated unions,
and two-layer validation (schema-level constraints + city bounds runtime checks).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class BuildRoadCmd(BaseModel):
    """Command to construct a road segment between two points."""

    model_config = ConfigDict(extra="forbid")

    cmd: Literal["build_road"] = "build_road"
    x0: int = Field(..., ge=0, description="Starting grid X coordinate")
    y0: int = Field(..., ge=0, description="Starting grid Y coordinate")
    x1: int = Field(..., ge=0, description="Ending grid X coordinate")
    y1: int = Field(..., ge=0, description="Ending grid Y coordinate")
    road_type: str = Field(default="$road00", min_length=1, description="Road draft ID or friendly alias")
    level: int = Field(default=0, ge=-2, le=2, description="Elevation level: -2 (tunnel) to 2 (elevated bridge)")

    @property
    def tile_length(self) -> int:
        """Calculates Manhattan grid length in tiles (inclusive)."""
        return abs(self.x1 - self.x0) + abs(self.y1 - self.y0) + 1

    def check_bounds(self, city_width: int, city_height: int) -> list[str]:
        """Validates that road endpoints lie within the city boundaries."""
        errs: list[str] = []
        if self.x0 >= city_width or self.x1 >= city_width:
            errs.append(f"Road X coordinates ({self.x0}, {self.x1}) out of bounds (width: {city_width})")
        if self.y0 >= city_height or self.y1 >= city_height:
            errs.append(f"Road Y coordinates ({self.y0}, {self.y1}) out of bounds (height: {city_height})")
        return errs


class BuildZoneCmd(BaseModel):
    """Command to designate zoning over a rectangular area."""

    model_config = ConfigDict(extra="forbid")

    cmd: Literal["build_zone"] = "build_zone"
    x: int = Field(..., ge=0, description="Upper-left origin X")
    y: int = Field(..., ge=0, description="Upper-left origin Y")
    width: int = Field(default=1, gt=0, description="Zone width in tiles")
    height: int = Field(default=1, gt=0, description="Zone height in tiles")
    zone_type: str = Field(default="residential_low", min_length=1, description="Zone type alias or draft ID")

    @property
    def tile_count(self) -> int:
        """Calculates total tile area."""
        return self.width * self.height

    def check_bounds(self, city_width: int, city_height: int) -> list[str]:
        """Validates that the zoned area does not exceed city boundaries."""
        errs: list[str] = []
        if self.x + self.width > city_width:
            errs.append(f"Zone horizontal span ({self.x}+{self.width}) exceeds city width ({city_width})")
        if self.y + self.height > city_height:
            errs.append(f"Zone vertical span ({self.y}+{self.height}) exceeds city height ({city_height})")
        return errs


class BuildBuildingCmd(BaseModel):
    """Command to place a specific building draft."""

    model_config = ConfigDict(extra="forbid")

    cmd: Literal["build_building"] = "build_building"
    x: int = Field(..., ge=0, description="Upper-left origin X")
    y: int = Field(..., ge=0, description="Upper-left origin Y")
    building_id: str = Field(..., min_length=1, description="Building draft ID or catalog alias")
    rotation: int = Field(default=0, ge=0, le=3, description="Rotation: 0, 1, 2, or 3")

    def check_bounds(self, city_width: int, city_height: int, footprint_w: int = 1, footprint_h: int = 1) -> list[str]:
        """Validates that the building footprint lies within city boundaries."""
        errs: list[str] = []
        if self.x + footprint_w > city_width:
            errs.append(f"Building X ({self.x}+{footprint_w}) exceeds city width ({city_width})")
        if self.y + footprint_h > city_height:
            errs.append(f"Building Y ({self.y}+{footprint_h}) exceeds city height ({city_height})")
        return errs


class BuildUtilityCmd(BaseModel):
    """Command to lay underground pipes or power wires."""

    model_config = ConfigDict(extra="forbid")

    cmd: Literal["build_utility"] = "build_utility"
    x0: int = Field(..., ge=0, description="Starting X")
    y0: int = Field(..., ge=0, description="Starting Y")
    x1: int = Field(..., ge=0, description="Ending X")
    y1: int = Field(..., ge=0, description="Ending Y")
    utility_type: Literal["pipe", "wire"] = Field(default="pipe", description="Utility kind: pipe or wire")

    @property
    def tile_length(self) -> int:
        """Calculates Manhattan grid length in tiles (inclusive)."""
        return abs(self.x1 - self.x0) + abs(self.y1 - self.y0) + 1

    def check_bounds(self, city_width: int, city_height: int) -> list[str]:
        """Validates that utility line endpoints lie within the city boundaries."""
        errs: list[str] = []
        if self.x0 >= city_width or self.x1 >= city_width:
            errs.append(f"Utility X ({self.x0}, {self.x1}) exceeds city width ({city_width})")
        if self.y0 >= city_height or self.y1 >= city_height:
            errs.append(f"Utility Y ({self.y0}, {self.y1}) exceeds city height ({city_height})")
        return errs


class DemolishCmd(BaseModel):
    """Command to demolish structures or clear terrain."""

    model_config = ConfigDict(extra="forbid")

    cmd: Literal["demolish"] = "demolish"
    x: int = Field(..., ge=0, description="Upper-left origin X")
    y: int = Field(..., ge=0, description="Upper-left origin Y")
    width: int = Field(default=1, gt=0, description="Area width in tiles")
    height: int = Field(default=1, gt=0, description="Area height in tiles")

    @property
    def tile_count(self) -> int:
        """Calculates total tile area to demolish."""
        return self.width * self.height

    def check_bounds(self, city_width: int, city_height: int) -> list[str]:
        """Validates that the demolition area does not exceed city boundaries."""
        errs: list[str] = []
        if self.x + self.width > city_width:
            errs.append(f"Demolish X ({self.x}+{self.width}) exceeds city width ({city_width})")
        if self.y + self.height > city_height:
            errs.append(f"Demolish Y ({self.y}+{self.height}) exceeds city height ({city_height})")
        return errs


# Discriminated union of all plan commands
PlanCommand = Annotated[
    BuildRoadCmd | BuildZoneCmd | BuildBuildingCmd | BuildUtilityCmd | DemolishCmd,
    Field(discriminator="cmd"),
]

# Alias for backwards and cross-spec compatibility
CityCommand = PlanCommand

# Type adapter for polymorphic list deserialization
plan_command_adapter: TypeAdapter[PlanCommand] = TypeAdapter(PlanCommand)
plan_command_list_adapter: TypeAdapter[list[PlanCommand]] = TypeAdapter(list[PlanCommand])


MAX_COMMANDS_PER_PLAN: int = 250
MAX_AFFECTED_TILES: int = 10000

JOB_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_job_id(job_id: str) -> str:
    """Validates job ID format preventing injection and invalid characters."""
    if not isinstance(job_id, str) or not JOB_ID_REGEX.fullmatch(job_id):
        raise ValueError(f"Invalid job_id '{job_id}'. Must match pattern ^[a-zA-Z0-9_-]{{1,64}}$")
    return job_id


class PlanValidationResult(BaseModel):
    """Result of a dry-run plan validation check."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_cost: int = 0
    command_count: int = 0
    affected_tiles: int = 0


class JobStatus(BaseModel):
    """Status and progress tracking for an asynchronous construction job."""

    job_id: str
    status: Literal["pending", "running", "cancel_requested", "completed", "failed", "cancelled"]
    session_id: str = ""
    progress: float = 0.0
    total_steps: int = 0
    completed_steps: int = 0
    attempted_steps: int = 0
    failed_steps: int = 0
    created_at: float
    updated_at: float
    error: str | None = None
    result: dict[str, Any] | None = None


class CityTelemetry(BaseModel):
    """Telemetry data representing the active city simulation state."""

    name: str = "Unknown"
    protocol: int = 0
    session_id: str = ""
    money: int = 0
    income: int = 0
    population: int = 0
    people: int | None = None
    happiness: float = 100.0
    happiness_by_category: dict[str, float] = Field(default_factory=dict)
    population_by_level: dict[str, int] = Field(default_factory=dict)
    demand: dict[str, int] = Field(default_factory=dict)
    taxes: dict[str, float] = Field(default_factory=dict)
    infrastructure: dict[str, int] = Field(default_factory=dict)
    utilities: dict[str, dict[str, Any]] = Field(default_factory=dict)
    service_coverage: dict[str, dict[str, Any]] = Field(default_factory=dict)
    problems: dict[str, Any] = Field(default_factory=dict)
    diagnostics_updated_at: float = 0.0
    diagnostics_error: str | None = None
    width: int = 128
    height: int = 128
    year: int = 2000
    month: int = 1
    day: int = 1
    speed: Literal[0, 1, 2, 3, 4] = 1
    connected: bool = True
    last_update: float = 0.0
    reason: str | None = None
    disaster: str | None = None
    is_sandbox: bool = False


def parse_command(data: Any) -> PlanCommand:
    """Parses a raw dictionary or command object into a validated PlanCommand."""
    if isinstance(data, (BuildRoadCmd, BuildZoneCmd, BuildBuildingCmd, BuildUtilityCmd, DemolishCmd)):
        return data
    return plan_command_adapter.validate_python(data)


def parse_commands(commands: Sequence[Any]) -> list[PlanCommand]:
    """Parses an iterable of command dictionaries or instances into validated PlanCommands."""
    return plan_command_list_adapter.validate_python(list(commands))
