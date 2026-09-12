"""
Tier 1: Feature F08 — City Telemetry Collector
5 Isolated Test Cases.
"""

from __future__ import annotations

from tests.e2e.conftest import MockTheoTownEnv


class TestFeatureF08TelemetryCollector:
    def test_e2e_t1_f08_01_all_10_core_fields(self, mock_env: MockTheoTownEnv):
        """Telemetry includes name, money, population, happiness, width, height, year, month, day, speed."""
        telem = mock_env.oracle.get_telemetry_dict()
        required_fields = ["name", "money", "population", "happiness", "width", "height", "year", "month", "day", "speed"]
        for f in required_fields:
            assert f in telem, f"Missing telemetry field: {f}"

    def test_e2e_t1_f08_02_population_mapping(self, mock_env: MockTheoTownEnv):
        """Telemetry accurately serializes population."""
        mock_env.oracle.population = 2450
        telem = mock_env.oracle.get_telemetry_dict()
        assert telem["population"] == 2450

    def test_e2e_t1_f08_03_treasury_balance(self, mock_env: MockTheoTownEnv):
        """Treasury balance tracking via money field."""
        mock_env.oracle.money = 85400
        telem = mock_env.oracle.get_telemetry_dict()
        assert telem["money"] == 85400

    def test_e2e_t1_f08_04_map_dimensions(self, mock_env: MockTheoTownEnv):
        """Grid dimension fields match simulation size."""
        mock_env.oracle.width = 128
        mock_env.oracle.height = 128
        telem = mock_env.oracle.get_telemetry_dict()
        assert telem["width"] == 128
        assert telem["height"] == 128

    def test_e2e_t1_f08_05_date_calendar_advancement(self, mock_env: MockTheoTownEnv):
        """Simulation date advances day and month."""
        mock_env.oracle.day = 29
        mock_env.oracle.month = 2
        mock_env.oracle.advance_time(days=3)  # Advances into month 3
        telem = mock_env.oracle.get_telemetry_dict()
        assert telem["month"] == 3
        assert telem["day"] == 2
