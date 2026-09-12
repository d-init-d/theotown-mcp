"""
Tier 1: Feature F09 — Dynamic Draft Catalog Discovery
5 Isolated Test Cases.
"""

from __future__ import annotations

import json

from tests.e2e.conftest import MockTheoTownEnv


class TestFeatureF09DraftDiscovery:
    def test_e2e_t1_f09_01_enumerate_drafts(self, mock_env: MockTheoTownEnv):
        """Verify baseline vanilla drafts enumerated in catalog."""
        drafts = mock_env.catalog.search_drafts()
        assert len(drafts) >= 15
        ids = [d["id"] for d in drafts]
        assert "$road01" in ids
        assert "$road03" in ids
        assert "$zone_residential_0" in ids

    def test_e2e_t1_f09_02_extract_metadata(self, mock_env: MockTheoTownEnv):
        """Draft metadata attributes (id, type, price) present."""
        draft = mock_env.catalog.get_draft("$road03")
        assert draft is not None
        assert draft["id"] == "$road03"
        assert draft["type"] == "road"
        assert draft["price"] == 50

    def test_e2e_t1_f09_03_filter_by_type_tag(self, mock_env: MockTheoTownEnv):
        """Filter drafts by category or type tag."""
        road_drafts = mock_env.catalog.search_drafts(category="road")
        assert len(road_drafts) >= 4
        assert all(d.get("category") == "road" or d.get("type") == "road" for d in road_drafts)

    def test_e2e_t1_f09_04_custom_plugin_draft_discovery(self, mock_env: MockTheoTownEnv):
        """Discovery of custom drafts from drafts.json."""
        custom_draft = {
            "id": "$sample_building_plugin00",
            "title": "Sample Modded Building",
            "category": "commercial",
            "type": "building",
            "price": 3000,
        }
        mock_env.config.drafts_path.write_text(json.dumps([custom_draft]), encoding="utf-8")
        mock_env.catalog.refresh()

        found = mock_env.catalog.get_draft("$sample_building_plugin00")
        assert found is not None
        assert found["title"] == "Sample Modded Building"

    def test_e2e_t1_f09_05_export_catalog_cache(self, mock_env: MockTheoTownEnv):
        """Verify drafts cache file exists and is valid JSON."""
        cached_file = mock_env.config.drafts_path
        cached_file.write_text(json.dumps(list(mock_env.catalog.drafts.values())), encoding="utf-8")
        assert cached_file.exists()
        loaded = json.loads(cached_file.read_text(encoding="utf-8"))
        assert isinstance(loaded, list)
