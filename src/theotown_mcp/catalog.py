"""
Runtime draft catalog manager and alias resolution system for TheoTown MCP Server.
Provides friendly name mapping, offline price estimation, and dynamic catalog discovery.
"""

from __future__ import annotations

import json
from typing import Any

from theotown_mcp.config import TheoTownConfig, get_config
from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildUtilityCmd,
    BuildZoneCmd,
    DemolishCmd,
    PlanCommand,
)

# Canonical alias mapping: friendly names to TheoTown draft IDs
DEFAULT_ALIASES: dict[str, str] = {
    # Roads
    "two_lane_road": "$road03",
    "road": "$road03",
    "dirt_road": "$road01",
    "country_road": "$road02",
    "avenue": "$road04",
    "highway": "$road_highway00",
    "expressway": "$road_highway01",
    "one_way_road": "$road_oneway00",
    "bridge": "$bridge00",
    # Zones
    "residential_low": "$zone_residential_0",
    "residential_low_alt": "$zone_residential_low00",
    "residential_medium": "$zone_residential_1",
    "residential_high": "$zone_residential_2",
    "commercial_low": "$zone_commercial_0",
    "commercial_medium": "$zone_commercial_1",
    "commercial_high": "$zone_commercial_2",
    "industrial_low": "$zone_industrial_0",
    "industrial_medium": "$zone_industrial_1",
    "industrial_high": "$zone_industrial_2",
    "residential": "$zone_residential_0",
    "commercial": "$zone_commercial_0",
    "industrial": "$zone_industrial_0",
    # Utilities
    "water_tower": "$watertower00",
    "wind_turbine": "$windturbine00",
    "solar_plant": "$solarplant00",
    "solar": "$solarplant00",
    "coal_power": "$coalpower00",
    "pipe": "$pipe00",
    "wire": "$wire00",
    # Public Services
    "small_park": "$park00",
    "park": "$park00",
    "fire_station": "$firestation00",
    "police_station": "$policestation00",
    "hospital": "$hospital00",
    "school": "$school00",
}

# Offline default price catalog (in TheoTown credits/Theons)
DEFAULT_PRICING: dict[str, int] = {
    "$road01": 20,
    "$road02": 35,
    "$road03": 50,
    "$road04": 120,
    "$road_highway00": 200,
    "$road_highway01": 250,
    "$road_oneway00": 40,
    "$zone_residential_0": 10,
    "$zone_residential_low00": 10,
    "$zone_residential_1": 25,
    "$zone_residential_2": 50,
    "$zone_commercial_0": 15,
    "$zone_commercial_1": 35,
    "$zone_commercial_2": 70,
    "$zone_industrial_0": 12,
    "$zone_industrial_1": 30,
    "$zone_industrial_2": 60,
    "$pipe00": 20,
    "$wire00": 15,
    "$watertower00": 2500,
    "$windturbine00": 4000,
    "$solarplant00": 8000,
    "$coalpower00": 15000,
    "$park00": 500,
    "$firestation00": 3000,
    "$policestation00": 3500,
    "$hospital00": 10000,
    "$school00": 5000,
}

# Baseline default catalog entries for vanilla game drafts
DEFAULT_DRAFTS: list[dict[str, Any]] = [
    {"id": "$road01", "title": "Dirt Road", "category": "road", "type": "road", "price": 20, "description": "Unpaved dirt track"},
    {"id": "$road02", "title": "Country Road", "category": "road", "type": "road", "price": 35, "description": "Basic country road"},
    {"id": "$road03", "title": "Two-Lane Road", "category": "road", "type": "road", "price": 50, "description": "Standard paved two-lane city street"},
    {"id": "$road04", "title": "Four-Lane Avenue", "category": "road", "type": "road", "price": 120, "description": "High-capacity four-lane avenue"},
    {"id": "$zone_residential_0", "title": "Low Density Residential", "category": "zone", "type": "zone", "price": 10, "description": "Single-family suburban housing"},
    {"id": "$zone_residential_1", "title": "Medium Density Residential", "category": "zone", "type": "zone", "price": 25, "description": "Townhouses and apartments"},
    {"id": "$zone_residential_2", "title": "High Density Residential", "category": "zone", "type": "zone", "price": 50, "description": "High-rise condominiums"},
    {"id": "$zone_commercial_0", "title": "Low Density Commercial", "category": "zone", "type": "zone", "price": 15, "description": "Local corner stores"},
    {"id": "$zone_commercial_1", "title": "Medium Density Commercial", "category": "zone", "type": "zone", "price": 35, "description": "Shopping centers and offices"},
    {"id": "$zone_commercial_2", "title": "High Density Commercial", "category": "zone", "type": "zone", "price": 70, "description": "Corporate towers and skyscrapers"},
    {"id": "$zone_industrial_0", "title": "Light Industrial", "category": "zone", "type": "zone", "price": 12, "description": "Workshops and warehouses"},
    {"id": "$zone_industrial_1", "title": "Medium Industrial", "category": "zone", "type": "zone", "price": 30, "description": "Manufacturing facilities"},
    {"id": "$zone_industrial_2", "title": "Heavy Industrial", "category": "zone", "type": "zone", "price": 60, "description": "Heavy industrial plants"},
    {"id": "$watertower00", "title": "Water Tower", "category": "water", "type": "building", "price": 2500, "description": "Stores and distributes clean water"},
    {"id": "$windturbine00", "title": "Wind Turbine", "category": "energy", "type": "building", "price": 4000, "description": "Eco-friendly wind power generator"},
    {"id": "$solarplant00", "title": "Solar Power Plant", "category": "energy", "type": "building", "price": 8000, "description": "Clean solar energy array"},
    {"id": "$coalpower00", "title": "Coal Power Plant", "category": "energy", "type": "building", "price": 15000, "description": "High-output coal power plant"},
    {"id": "$park00", "title": "Small Park", "category": "park", "type": "building", "price": 500, "description": "Green urban park raising happiness"},
    {"id": "$pipe00", "title": "Water Pipe", "category": "utility", "type": "utility", "price": 20, "description": "Subterranean water distribution pipe"},
    {"id": "$wire00", "title": "Power Line", "category": "utility", "type": "utility", "price": 15, "description": "Overhead electrical transmission cable"},
]


class DraftCatalog:
    """Manages draft lookup, friendly alias mapping, and pricing calculations."""

    def __init__(self, config: TheoTownConfig | None = None) -> None:
        self.config = config or get_config()
        self.aliases: dict[str, str] = dict(DEFAULT_ALIASES)
        self.drafts: dict[str, dict[str, Any]] = {d["id"]: dict(d) for d in DEFAULT_DRAFTS}
        self.pricing: dict[str, int] = dict(DEFAULT_PRICING)
        self._load_cached_drafts()

    def _load_cached_drafts(self) -> None:
        """Loads cached drafts exported by the Lua plugin if drafts.json exists."""
        drafts_file = self.config.drafts_path
        if drafts_file.exists():
            import contextlib
            with contextlib.suppress(OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
                data = json.loads(drafts_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict) and "id" in entry:
                            draft_id = entry["id"]
                            self.drafts[draft_id] = entry
                            if "price" in entry and isinstance(entry["price"], (int, float)):
                                self.pricing[draft_id] = int(entry["price"])

    def refresh(self) -> None:
        """Refreshes draft cache from disk."""
        self._load_cached_drafts()

    def resolve_draft_id(self, alias_or_id: str) -> str:
        """
        Resolves an alias or native draft ID.
        Returns native draft ID (e.g. 'two_lane_road' -> '$road03').
        """
        clean_key = alias_or_id.strip()
        if clean_key in self.aliases:
            return self.aliases[clean_key]

        # Case-insensitive alias matching
        lower_key = clean_key.lower()
        if lower_key in self.aliases:
            return self.aliases[lower_key]

        return clean_key

    def get_draft(self, alias_or_id: str) -> dict[str, Any] | None:
        """Finds draft metadata by alias or native ID."""
        resolved = self.resolve_draft_id(alias_or_id)
        return self.drafts.get(resolved)

    def search_drafts(
        self,
        category: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        """Searches loaded drafts by category and text query."""
        results: list[dict[str, Any]] = []
        q = query.lower().strip() if query else None
        cat = category.lower().strip() if category else None

        for draft in self.drafts.values():
            if cat:
                draft_cat = str(draft.get("category", "")).lower()
                draft_type = str(draft.get("type", "")).lower()
                if cat not in (draft_cat, draft_type):
                    continue

            if q:
                d_id = str(draft.get("id", "")).lower()
                d_title = str(draft.get("title", "")).lower()
                d_desc = str(draft.get("description", "")).lower()
                if q not in d_id and q not in d_title and q not in d_desc:
                    continue

            results.append(draft)

        return results

    def estimate_unit_price(self, draft_id_or_alias: str, default_price: int = 50) -> int:
        """Retrieves estimated unit cost for a draft ID."""
        resolved = self.resolve_draft_id(draft_id_or_alias)
        if resolved in self.pricing:
            return self.pricing[resolved]
        if resolved in self.drafts:
            price = self.drafts[resolved].get("price")
            if isinstance(price, (int, float)):
                return int(price)
        return default_price

    def estimate_command_cost(self, cmd: PlanCommand) -> int:
        """Estimates credit cost for an individual construction command."""
        if isinstance(cmd, BuildRoadCmd):
            unit_price = self.estimate_unit_price(cmd.road_type, default_price=50)
            return cmd.tile_length * unit_price

        if isinstance(cmd, BuildZoneCmd):
            unit_price = self.estimate_unit_price(cmd.zone_type, default_price=10)
            return cmd.tile_count * unit_price

        if isinstance(cmd, BuildBuildingCmd):
            return self.estimate_unit_price(cmd.building_id, default_price=500)

        if isinstance(cmd, BuildUtilityCmd):
            fallback = 20 if cmd.utility_type == "pipe" else 15
            unit_price = self.estimate_unit_price(f"${cmd.utility_type}00", default_price=fallback)
            return cmd.tile_length * unit_price

        if isinstance(cmd, DemolishCmd):
            # Demolition standard cost in TheoTown is ~5 credits per tile
            return cmd.tile_count * 5

        return 0

    def estimate_total_cost(self, commands: list[PlanCommand]) -> int:
        """Calculates total estimated cost for a list of commands."""
        return sum(self.estimate_command_cost(cmd) for cmd in commands)


_global_catalog: DraftCatalog | None = None


def get_catalog(config: TheoTownConfig | None = None, refresh: bool = False) -> DraftCatalog:
    """Retrieves or initializes the global DraftCatalog singleton."""
    global _global_catalog
    if _global_catalog is None or refresh:
        _global_catalog = DraftCatalog(config=config)
    return _global_catalog
