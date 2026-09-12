"""
Unit tests for draft catalog manager, alias resolution,
and price estimation in theotown_mcp.catalog.
"""

from __future__ import annotations

import json

from theotown_mcp.catalog import DraftCatalog
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.models import (
    BuildBuildingCmd,
    BuildRoadCmd,
    BuildUtilityCmd,
    BuildZoneCmd,
    DemolishCmd,
)


class TestDraftCatalogAliases:
    def test_default_aliases_present(self, mock_catalog: DraftCatalog):
        assert "two_lane_road" in mock_catalog.aliases
        assert "residential_low" in mock_catalog.aliases
        assert "solar" in mock_catalog.aliases
        assert "pipe" in mock_catalog.aliases
        assert "park" in mock_catalog.aliases

    def test_resolve_draft_id_exact(self, mock_catalog: DraftCatalog):
        assert mock_catalog.resolve_draft_id("two_lane_road") == "$road03"
        assert mock_catalog.resolve_draft_id("residential_low") == "$zone_residential_0"
        assert mock_catalog.resolve_draft_id("solar") == "$solarplant00"
        assert mock_catalog.resolve_draft_id("pipe") == "$pipe00"

    def test_resolve_draft_id_case_insensitive_and_whitespace(self, mock_catalog: DraftCatalog):
        assert mock_catalog.resolve_draft_id("  TWO_LANE_ROAD  ") == "$road03"
        assert mock_catalog.resolve_draft_id("Residential_Low") == "$zone_residential_0"
        assert mock_catalog.resolve_draft_id("SOLAR") == "$solarplant00"

    def test_resolve_draft_id_passthrough_native_or_unknown(self, mock_catalog: DraftCatalog):
        assert mock_catalog.resolve_draft_id("$road03") == "$road03"
        assert mock_catalog.resolve_draft_id("$my_custom_plugin_draft") == "$my_custom_plugin_draft"
        assert mock_catalog.resolve_draft_id("unregistered_name") == "unregistered_name"


class TestDraftCatalogLookupAndSearch:
    def test_get_draft_by_id_and_alias(self, mock_catalog: DraftCatalog):
        # By ID
        draft_id = mock_catalog.get_draft("$road03")
        assert draft_id is not None
        assert draft_id["id"] == "$road03"
        assert draft_id["price"] == 50

        # By Alias
        draft_alias = mock_catalog.get_draft("two_lane_road")
        assert draft_alias is not None
        assert draft_alias["id"] == "$road03"

        # Non-existent
        assert mock_catalog.get_draft("$non_existent_id") is None

    def test_search_drafts_by_query(self, mock_catalog: DraftCatalog):
        results = mock_catalog.search_drafts(query="road")
        assert len(results) >= 4
        assert all("road" in d["id"].lower() or "road" in d["title"].lower() for d in results)

    def test_search_drafts_by_category(self, mock_catalog: DraftCatalog):
        zone_results = mock_catalog.search_drafts(category="zone")
        assert len(zone_results) >= 6
        assert all(d["category"] == "zone" or d["type"] == "zone" for d in zone_results)

        energy_results = mock_catalog.search_drafts(category="energy")
        assert len(energy_results) >= 3

    def test_search_drafts_combined_and_no_match(self, mock_catalog: DraftCatalog):
        results = mock_catalog.search_drafts(category="road", query="dirt")
        assert len(results) == 1
        assert results[0]["id"] == "$road01"

        no_match = mock_catalog.search_drafts(query="spaceship_galaxy_portal")
        assert no_match == []


class TestDraftCatalogDynamicCaching:
    def test_load_cached_drafts(self, mock_config: TheoTownConfig):
        # Write mock drafts.json to plugin directory
        custom_drafts = [
            {
                "id": "$custom_skyscraper01",
                "title": "Neon Tower",
                "category": "commercial",
                "type": "building",
                "price": 25000,
                "description": "High tech skyscraper",
            }
        ]
        mock_config.drafts_path.parent.mkdir(parents=True, exist_ok=True)
        mock_config.drafts_path.write_text(json.dumps(custom_drafts), encoding="utf-8")

        catalog = DraftCatalog(config=mock_config)
        assert "$custom_skyscraper01" in catalog.drafts
        assert catalog.estimate_unit_price("$custom_skyscraper01") == 25000

        # Refresh
        catalog.refresh()
        assert catalog.get_draft("$custom_skyscraper01")["title"] == "Neon Tower"

    def test_corrupted_drafts_json_handled_gracefully(self, mock_config: TheoTownConfig):
        mock_config.drafts_path.write_text("INVALID_JSON", encoding="utf-8")
        catalog = DraftCatalog(config=mock_config)
        # Still retains default drafts
        assert "$road03" in catalog.drafts


class TestPriceEstimation:
    def test_estimate_unit_price(self, mock_catalog: DraftCatalog):
        assert mock_catalog.estimate_unit_price("$road03") == 50
        assert mock_catalog.estimate_unit_price("two_lane_road") == 50
        assert mock_catalog.estimate_unit_price("$zone_residential_0") == 10
        assert mock_catalog.estimate_unit_price("solar") == 8000
        # Unknown falls back to default_price
        assert mock_catalog.estimate_unit_price("mystery_item", default_price=999) == 999

    def test_estimate_command_cost(self, mock_catalog: DraftCatalog):
        # Road: 11 tiles of $road03 (50 each) = 550
        road_cmd = BuildRoadCmd(x0=10, y0=10, x1=20, y1=10, road_type="$road03")
        assert mock_catalog.estimate_command_cost(road_cmd) == 11 * 50

        # Zone: 16 tiles of low residential (10 each) = 160
        zone_cmd = BuildZoneCmd(x=0, y=0, width=4, height=4, zone_type="residential_low")
        assert mock_catalog.estimate_command_cost(zone_cmd) == 16 * 10

        # Building: solar plant = 8000
        bldg_cmd = BuildBuildingCmd(x=5, y=5, building_id="solar")
        assert mock_catalog.estimate_command_cost(bldg_cmd) == 8000

        # Utility: 10 tiles of pipe (20 each) = 200
        pipe_cmd = BuildUtilityCmd(x0=0, y0=0, x1=9, y1=0, utility_type="pipe")
        assert mock_catalog.estimate_command_cost(pipe_cmd) == 10 * 20

        # Utility: 10 tiles of wire (15 each) = 150
        wire_cmd = BuildUtilityCmd(x0=0, y0=0, x1=9, y1=0, utility_type="wire")
        assert mock_catalog.estimate_command_cost(wire_cmd) == 10 * 15

        # Demolish: 9 tiles (5 each) = 45
        demo_cmd = DemolishCmd(x=0, y=0, width=3, height=3)
        assert mock_catalog.estimate_command_cost(demo_cmd) == 9 * 5

    def test_estimate_total_cost(self, mock_catalog: DraftCatalog):
        commands = [
            BuildRoadCmd(x0=0, y0=0, x1=9, y1=0, road_type="$road03"),  # 10 * 50 = 500
            BuildZoneCmd(x=0, y=1, width=2, height=2, zone_type="residential_low"),  # 4 * 10 = 40
            DemolishCmd(x=10, y=10, width=2, height=2),  # 4 * 5 = 20
        ]
        total = mock_catalog.estimate_total_cost(commands)
        assert total == 500 + 40 + 20
