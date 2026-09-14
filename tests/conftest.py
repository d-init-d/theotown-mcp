"""
Pytest configuration and shared fixtures for TheoTown MCP Server tests.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from theotown_mcp.bridge import TheoTownBridge
from theotown_mcp.catalog import DraftCatalog
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.server import MCPServer, create_server


@pytest.fixture
def mock_theotown_dir(tmp_path: Path) -> Path:
    """Creates a temporary mock TheoTown data directory."""
    tt_dir = tmp_path / "TheoTown"
    tt_dir.mkdir(parents=True, exist_ok=True)
    (tt_dir / "plugins" / "theotown_mcp").mkdir(parents=True, exist_ok=True)
    return tt_dir


@pytest.fixture
def mock_config(mock_theotown_dir: Path) -> TheoTownConfig:
    """Provides a TheoTownConfig pointed at the temporary mock directory."""
    return TheoTownConfig(data_dir_override=mock_theotown_dir)


@pytest.fixture
def mock_telemetry_file(mock_config: TheoTownConfig) -> Path:
    """Creates a mock telemetry.json file with realistic city simulation metrics."""
    telemetry_data = {
        "protocol": 2,
        "session_id": "unit-test-city",
        "name": "EmeraldCity",
        "money": 75000,
        "income": 4200,
        "population": 1250,
        "happiness": 88.5,
        "happiness_by_category": {"health": 62.0, "supply": 91.0},
        "population_by_level": {"low": 800, "middle": 350, "high": 100},
        "demand": {"residential_capacity": 1500, "commercial_jobs": 700, "industrial_jobs": 600},
        "taxes": {"residential_low": 7.0},
        "infrastructure": {"roads": 420, "medical_buildings": 3},
        "utilities": {
            "power": {
                "estimated_production": 1000,
                "estimated_consumption": 920,
                "estimated_reserve": 80,
                "utilization_percent": 92.0,
                "adequate": True,
            }
        },
        "service_coverage": {
            "health": {
                "average_percent": 55.0,
                "under_threshold_percent": 28.0,
                "samples": 100,
                "threshold_percent": 35.0,
                "weak_locations": [{"x": 80, "y": 12, "value_percent": 5.0}],
            }
        },
        "problems": {"sampled_rci_buildings": 100, "sample_counts": {"ill": 4}},
        "diagnostics_updated_at": time.time(),
        "width": 128,
        "height": 128,
        "year": 2026,
        "month": 9,
        "day": 12,
        "speed": 1,
        "connected": True,
        "last_updated": time.time(),
    }
    path = mock_config.telemetry_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(telemetry_data, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def mock_catalog(mock_config: TheoTownConfig) -> DraftCatalog:
    """Provides a fresh DraftCatalog instance."""
    return DraftCatalog(config=mock_config)


@pytest.fixture
def mock_bridge(mock_config: TheoTownConfig, mock_catalog: DraftCatalog, mock_telemetry_file: Path) -> TheoTownBridge:
    """Provides a TheoTownBridge connected to mock configuration and catalog."""
    return TheoTownBridge(config=mock_config, catalog=mock_catalog)


@pytest.fixture
def mock_server(
    mock_config: TheoTownConfig,
    mock_bridge: TheoTownBridge,
    mock_catalog: DraftCatalog,
) -> MCPServer:
    """Provides a fully initialized MCPServer instance with mock bridge and catalog."""
    return create_server(config=mock_config, bridge=mock_bridge, catalog=mock_catalog)
