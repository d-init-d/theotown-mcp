"""
Tier 1: Feature F14 — Runtime Draft Catalog Manager
5 Isolated Test Cases.
"""

from __future__ import annotations

from tests.e2e.conftest import MockTheoTownEnv


class TestFeatureF14DraftCatalogManager:
    def test_e2e_t1_f14_01_friendly_alias_resolution(self, mock_env: MockTheoTownEnv):
        """Friendly alias maps to native draft ID."""
        assert mock_env.catalog.resolve_draft_id("two_lane_road") == "$road00"

    def test_e2e_t1_f14_02_native_id_identity(self, mock_env: MockTheoTownEnv):
        """Native draft ID resolves to itself."""
        assert mock_env.catalog.resolve_draft_id("$road03") == "$road03"

    def test_e2e_t1_f14_03_zone_alias_resolution(self, mock_env: MockTheoTownEnv):
        """Zone alias resolves to native zone draft ID."""
        assert mock_env.catalog.resolve_draft_id("residential_low") == "$zoneresidential"

    def test_e2e_t1_f14_04_search_drafts_by_text(self, mock_env: MockTheoTownEnv):
        """Search drafts by text query."""
        results = mock_env.catalog.search_drafts(query="solar")
        assert len(results) >= 1
        assert results[0]["id"] == "$solarplant00"

    def test_e2e_t1_f14_05_fallback_pricing_estimation(self, mock_env: MockTheoTownEnv):
        """Fallback pricing estimation for draft."""
        price = mock_env.catalog.estimate_unit_price("two_lane_road")
        assert price == 50
