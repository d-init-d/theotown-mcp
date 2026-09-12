"""
Tier 1: Feature F06 — Road Segmenting
5 Isolated Test Cases.
"""

from __future__ import annotations

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.city_oracle import slice_road_coordinates
from theotown_mcp.models import BuildRoadCmd


class TestFeatureF06RoadSegmenting:
    def test_e2e_t1_f06_01_short_road_bypass(self):
        """Roads <= 32 tiles are not sliced."""
        segments = slice_road_coordinates(10, 10, 25, 10, max_segment_length=32)
        assert len(segments) == 1
        assert segments[0] == (10, 10, 25, 10)

    def test_e2e_t1_f06_02_slice_48_tiles_into_2_segments(self):
        """48-tile road is sliced into exactly 2 segments."""
        segments = slice_road_coordinates(10, 10, 57, 10, max_segment_length=32)
        assert len(segments) == 2
        # Check boundary connectivity
        assert segments[0][2] == segments[1][0]
        assert segments[0][3] == segments[1][1]

    def test_e2e_t1_f06_03_slice_100_tiles_into_4_segments(self):
        """100-tile road is sliced into 4 segments."""
        segments = slice_road_coordinates(20, 10, 20, 109, max_segment_length=32)
        assert len(segments) == 4
        # Each segment length <= 32
        for s in segments:
            seg_len = max(abs(s[2] - s[0]), abs(s[3] - s[1]))
            assert seg_len <= 32

    def test_e2e_t1_f06_04_junction_continuity(self):
        """Adjacent slices share boundary junction tiles."""
        segments = slice_road_coordinates(0, 0, 70, 0, max_segment_length=32)
        for i in range(len(segments) - 1):
            assert (segments[i][2], segments[i][3]) == (segments[i + 1][0], segments[i + 1][1])

    def test_e2e_t1_f06_05_cost_preservation(self, mock_env: MockTheoTownEnv):
        """Total road price calculation is preserved for segmented roads."""
        cmd = BuildRoadCmd(x0=0, y0=0, x1=50, y1=0, road_type="$road03")
        cost = mock_env.catalog.estimate_command_cost(cmd)
        # 51 tiles * 50 = 2550
        assert cost == 51 * 50
