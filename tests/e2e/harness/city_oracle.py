"""
City Simulation Oracle for TheoTown MCP E2E testing.
Maintains authentic simulation state (grid, treasury, population, date, speed)
and executes operations according to official TheoTown Lua semantics.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from theotown_mcp.catalog import DraftCatalog
from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildUtilityCmd,
    BuildZoneCmd,
    DemolishCmd,
    PlanCommand,
)


def slice_road_coordinates(
    x0: int, y0: int, x1: int, y1: int, max_segment_length: int = 32
) -> list[tuple[int, int, int, int]]:
    """
    Slices a continuous road path into sub-segments of length <= max_segment_length.
    Adjacent sub-segments share boundary joint coordinates to ensure topological connectivity.
    """
    dx = x1 - x0
    dy = y1 - y0
    dist = max(abs(dx), abs(dy))
    num_tiles = dist + 1

    if num_tiles <= max_segment_length:
        return [(x0, y0, x1, y1)]

    segments: list[tuple[int, int, int, int]] = []
    num_segments = math.ceil(num_tiles / max_segment_length)
    curr_x, curr_y = x0, y0

    for i in range(num_segments):
        progress = (i + 1) / num_segments
        next_x = round(x0 + dx * progress)
        next_y = round(y0 + dy * progress)
        segments.append((curr_x, curr_y, next_x, next_y))
        curr_x, curr_y = next_x, next_y

    return segments


class CityOracle:
    """Headless simulation oracle representing TheoTown engine state."""

    def __init__(
        self,
        name: str = "TestTown",
        width: int = 128,
        height: int = 128,
        initial_money: int = 100000,
    ) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.money = initial_money
        self.population = 0
        self.happiness = 100.0
        self.year = 2026
        self.month = 1
        self.day = 1
        self.speed: Literal[0, 1, 2, 3, 4] = 1
        self.catalog = DraftCatalog()

        # Grid state: (x, y) -> dict of tile attributes
        self.grid: dict[tuple[int, int], dict[str, Any]] = {}

    def get_telemetry_dict(self) -> dict[str, Any]:
        """Returns telemetry representation matching telemetry.json schema."""
        return {
            "name": self.name,
            "money": self.money,
            "population": self.population,
            "people": self.population,
            "happiness": self.happiness,
            "width": self.width,
            "height": self.height,
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "speed": self.speed,
            "connected": True,
            "last_updated": 1746214197.0,
        }

    def is_in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_road_buildable(self, x0: int, y0: int, x1: int, y1: int, level: int = 0) -> bool:
        """Checks if road can be built without collision with non-demolishable entities."""
        if not self.is_in_bounds(x0, y0) or not self.is_in_bounds(x1, y1):
            return False
        # If any tile along the line has water and level == 0 without bridge
        dx = 1 if x1 > x0 else (-1 if x1 < x0 else 0)
        dy = 1 if y1 > y0 else (-1 if y1 < y0 else 0)
        cx, cy = x0, y0
        while True:
            tile = self.grid.get((cx, cy), {})
            if tile.get("water") and level == 0:
                return False
            if tile.get("indestructible"):
                return False
            if cx == x1 and cy == y1:
                break
            if cx != x1:
                cx += dx
            elif cy != y1:
                cy += dy
        return True

    def is_building_buildable(self, x: int, y: int, footprint_w: int = 1, footprint_h: int = 1) -> bool:
        """Checks if building footprint fits completely within empty terrain."""
        for cx in range(x, x + footprint_w):
            for cy in range(y, y + footprint_h):
                if not self.is_in_bounds(cx, cy):
                    return False
                tile = self.grid.get((cx, cy), {})
                if tile.get("building") or tile.get("water") or tile.get("indestructible"):
                    return False
        return True

    def is_zone_buildable(self, x: int, y: int, width: int, height: int) -> bool:
        """Checks if zoning fits within city bounds and non-water."""
        for cx in range(x, x + width):
            for cy in range(y, y + height):
                if not self.is_in_bounds(cx, cy):
                    return False
                tile = self.grid.get((cx, cy), {})
                if tile.get("water") or tile.get("indestructible"):
                    return False
        return True

    def is_removable(self, x: int, y: int, width: int, height: int) -> bool:
        for cx in range(x, x + width):
            for cy in range(y, y + height):
                if not self.is_in_bounds(cx, cy):
                    return False
                tile = self.grid.get((cx, cy), {})
                if tile.get("indestructible"):
                    return False
        return True

    def execute_command(self, cmd: PlanCommand) -> dict[str, Any]:
        """Executes a validated command directly on the city oracle."""
        cost = self.catalog.estimate_command_cost(cmd)
        if self.money < cost:
            return {"success": False, "error": "Insufficient funds", "cost": cost}

        if isinstance(cmd, BuildRoadCmd):
            if not self.is_road_buildable(cmd.x0, cmd.y0, cmd.x1, cmd.y1, cmd.level):
                return {"success": False, "error": "Path blocked or out of bounds", "cost": 0}
            self.money -= cost
            # Place road tiles
            segments = slice_road_coordinates(cmd.x0, cmd.y0, cmd.x1, cmd.y1)
            for s in segments:
                cx, cy, ex, ey = s
                dx = 1 if ex > cx else (-1 if ex < cx else 0)
                dy = 1 if ey > cy else (-1 if ey < cy else 0)
                while True:
                    self.grid.setdefault((cx, cy), {})["road"] = cmd.road_type
                    if cx == ex and cy == ey:
                        break
                    if cx != ex:
                        cx += dx
                    elif cy != ey:
                        cy += dy
            return {"success": True, "cost": cost, "segments": len(segments)}

        if isinstance(cmd, BuildZoneCmd):
            if not self.is_zone_buildable(cmd.x, cmd.y, cmd.width, cmd.height):
                return {"success": False, "error": "Zone blocked or out of bounds", "cost": 0}
            self.money -= cost
            for cx in range(cmd.x, cmd.x + cmd.width):
                for cy in range(cmd.y, cmd.y + cmd.height):
                    self.grid.setdefault((cx, cy), {})["zone"] = cmd.zone_type
            # Residential zones increase population capacity
            if "residential" in cmd.zone_type:
                self.population += cmd.tile_count * 10
            return {"success": True, "cost": cost}

        if isinstance(cmd, BuildBuildingCmd):
            if not self.is_building_buildable(cmd.x, cmd.y):
                return {"success": False, "error": "Building blocked or out of bounds", "cost": 0}
            self.money -= cost
            self.grid.setdefault((cmd.x, cmd.y), {})["building"] = cmd.building_id
            if "park" in cmd.building_id:
                self.happiness = min(100.0, self.happiness + 5.0)
            return {"success": True, "cost": cost}

        if isinstance(cmd, BuildUtilityCmd):
            self.money -= cost
            dx = 1 if cmd.x1 > cmd.x0 else (-1 if cmd.x1 < cmd.x0 else 0)
            dy = 1 if cmd.y1 > cmd.y0 else (-1 if cmd.y1 < cmd.y0 else 0)
            cx, cy = cmd.x0, cmd.y0
            while True:
                self.grid.setdefault((cx, cy), {})[cmd.utility_type] = True
                if cx == cmd.x1 and cy == cmd.y1:
                    break
                if cx != cmd.x1:
                    cx += dx
                elif cy != cmd.y1:
                    cy += dy
            return {"success": True, "cost": cost}

        if isinstance(cmd, DemolishCmd):
            if not self.is_removable(cmd.x, cmd.y, cmd.width, cmd.height):
                return {"success": False, "error": "Indestructible area", "cost": 0}
            self.money -= cost
            for cx in range(cmd.x, cmd.x + cmd.width):
                for cy in range(cmd.y, cmd.y + cmd.height):
                    self.grid.pop((cx, cy), None)
            return {"success": True, "cost": cost}

        return {"success": False, "error": f"Unknown command {cmd}", "cost": 0}

    def advance_time(self, days: int = 1) -> None:
        """Simulates calendar day progression with 30-day month model."""
        self.day += days
        while self.day > 30:
            self.day -= 30
            self.month += 1
            if self.month > 12:
                self.month = 1
                self.year += 1
        # Daily tax collection
        daily_tax = math.floor(self.population * 0.5)
        self.money += daily_tax * days
