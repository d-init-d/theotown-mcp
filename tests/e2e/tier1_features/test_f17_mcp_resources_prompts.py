"""
Tier 1: Feature F17 — MCP Server v2 Resources & Prompts
5 Isolated Test Cases.
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.conftest import MockTheoTownEnv


@pytest.mark.anyio
class TestFeatureF17MCPResourcesPrompts:
    async def test_e2e_t1_f17_01_read_city_status_resource(self, mock_env: MockTheoTownEnv):
        """Read resource theotown://city/status."""
        contents = await mock_env.server.read_resource("theotown://city/status")
        assert len(contents) == 1
        data = json.loads(contents[0].content)
        assert data["name"] == "E2ETestCity"

    async def test_e2e_t1_f17_02_read_catalog_drafts_resource(self, mock_env: MockTheoTownEnv):
        """Read resource theotown://catalog/drafts."""
        contents = await mock_env.server.read_resource("theotown://catalog/drafts")
        assert len(contents) == 1
        data = json.loads(contents[0].content)
        assert isinstance(data, list)

    async def test_e2e_t1_f17_03_get_urban_planner_prompt(self, mock_env: MockTheoTownEnv):
        """Retrieve urban_planner prompt."""
        res = await mock_env.server.get_prompt("urban_planner", {})
        assert len(res.messages) == 1
        assert "Road Hierarchy" in res.messages[0].content.text

    def test_e2e_t1_f17_04_resource_enumeration(self, mock_env: MockTheoTownEnv):
        """Enumerate registered server resources."""
        res_keys = list(mock_env.server._resource_manager._resources.keys())
        assert "theotown://city/status" in res_keys
        assert "theotown://catalog/drafts" in res_keys

    def test_e2e_t1_f17_05_prompt_enumeration(self, mock_env: MockTheoTownEnv):
        """Enumerate registered server prompts."""
        prompt_keys = list(mock_env.server._prompt_manager._prompts.keys())
        assert "urban_planner" in prompt_keys
