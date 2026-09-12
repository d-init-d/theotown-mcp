"""
Pytest configuration and fixtures for TheoTown MCP E2E test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.harness.bridge_simulator import BridgeSimulator
from tests.e2e.harness.city_oracle import CityOracle
from theotown_mcp.bridge import TheoTownBridge
from theotown_mcp.catalog import DraftCatalog
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.server import MCPServer, create_server


class MockTheoTownEnv:
    """Encapsulates a self-contained simulated TheoTown environment."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "TheoTown"
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = TheoTownConfig(data_dir_override=self.root)
        self.config.ensure_directories()

        self.oracle = CityOracle(name="E2ETestCity", width=128, height=128, initial_money=100000)
        self.catalog = DraftCatalog(config=self.config)
        self.bridge = TheoTownBridge(config=self.config, catalog=self.catalog)
        self.simulator = BridgeSimulator(config=self.config, oracle=self.oracle)

        # Seed initial telemetry file
        self.simulator.sync_telemetry_to_disk()

        # Seed server
        self.server = create_server(config=self.config, bridge=self.bridge, catalog=self.catalog)

    def tick(self) -> None:
        """Simulates one engine frame tick processing pending commands."""
        self.simulator.process_inbox()


@pytest.fixture
def mock_env(tmp_path: Path) -> MockTheoTownEnv:
    """Fixture providing a fresh isolated MockTheoTownEnv."""
    return MockTheoTownEnv(tmp_path)


@pytest.fixture
def e2e_oracle(mock_env: MockTheoTownEnv) -> CityOracle:
    return mock_env.oracle


@pytest.fixture
def e2e_bridge_sim(mock_env: MockTheoTownEnv) -> BridgeSimulator:
    return mock_env.simulator


@pytest.fixture
def e2e_bridge(mock_env: MockTheoTownEnv) -> TheoTownBridge:
    return mock_env.bridge


@pytest.fixture
def e2e_config(mock_env: MockTheoTownEnv) -> TheoTownConfig:
    return mock_env.config


@pytest.fixture
def e2e_server(mock_env: MockTheoTownEnv) -> MCPServer:
    return mock_env.server
