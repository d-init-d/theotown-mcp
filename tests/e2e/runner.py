"""
tests/e2e/runner.py
TheoTown MCP Server: Unified End-to-End Test Suite Runner.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pytest


def main() -> None:
    parser = argparse.ArgumentParser(description="TheoTown MCP E2E Test Suite Runner")
    parser.add_argument("--tier", choices=["1", "2", "3", "4", "all"], default="all", help="Test tier to execute")
    parser.add_argument("--feature", type=str, default=None, help="Filter by feature ID (e.g. F01, F15)")
    parser.add_argument("--mode", choices=["mock", "live", "auto"], default="auto", help="Execution mode (mock or live game)")
    parser.add_argument("--report-json", type=Path, default=None, help="Path to write JSON test report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose pytest output")
    args = parser.parse_args()

    pytest_args = ["-ra"]
    if args.verbose:
        pytest_args.append("-v")
    else:
        pytest_args.append("-q")

    # Tier selection
    test_dir = Path(__file__).parent
    if args.tier == "1":
        pytest_args.append(str(test_dir / "tier1_features"))
    elif args.tier == "2":
        pytest_args.append(str(test_dir / "tier2_boundaries"))
    elif args.tier == "3":
        pytest_args.append(str(test_dir / "tier3_combinations"))
    elif args.tier == "4":
        pytest_args.append(str(test_dir / "tier4_scenarios"))
    else:
        pytest_args.append(str(test_dir))

    # Feature filter
    if args.feature:
        pytest_args.extend(["-k", args.feature])

    # Mode selection
    if args.mode == "mock":
        pytest_args.extend(["-m", "not live"])
    elif args.mode == "live":
        pytest_args.extend(["-m", "live"])

    print("=" * 70)
    print(" TheoTown MCP Server: 4-Tier End-to-End (E2E) Test Suite")
    print(f" Target: {args.tier.upper()} | Mode: {args.mode.upper()} | Feature Filter: {args.feature or 'ALL'}")
    print("=" * 70)

    start_time = time.time()
    exit_code = pytest.main(pytest_args)
    duration = time.time() - start_time

    if args.report_json:
        report = {
            "timestamp": time.time(),
            "duration_seconds": duration,
            "tier": args.tier,
            "mode": args.mode,
            "exit_code": int(exit_code),
            "status": "PASS" if exit_code == 0 else "FAIL",
        }
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[*] Report saved to {args.report_json}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
