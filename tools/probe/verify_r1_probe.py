#!/usr/bin/env python3
"""
TheoTown MCP Server — Phase 0 IPC & Telemetry Ground-Truth Verification Probe
Filename: verify_r1_probe.py
Author: TheoTown MCP Architecture & Explorer Team (Milestone M0)

Tests and verifies Requirement R1 against the live TheoTown installation without mocking:
1. Inspects C:\\Users\\dmn05\\TheoTown\\.pmodext and parses the # JSON payload to verify canary token from TheoTown.getFileStorage().
2. Inspects C:\\Users\\dmn05\\.prefs\\theotown\\ for storage artifacts, including hashed SSP files (e.g. LSsdSvElX2ZethqZnh4DBg==).
3. Tests atomic writing to probe_inbox.lua (same-dir temp file + os.replace), waits for #LuaWrapper reload, and verifies cross-script handoff.
4. Reads and validates probe_telemetry.json schema and live city metrics (name, money, people, happiness, dimensions, speed).
5. Provides automated assertions and return codes (0 for PASS, non-zero for FAIL).
"""

import argparse
import base64
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

# Exit Code Constants
EXIT_SUCCESS = 0
EXIT_ASSERTION_FAILURE = 1
EXIT_TIMEOUT_OR_NOT_READY = 2
EXIT_FILESYSTEM_ERROR = 3

DEFAULT_CANARY_TOKEN = "CANARY_THEOTOWN_MCP_2026_TOKEN_01"


def get_default_paths() -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Resolves default TheoTown paths based on user profile and environment variables."""
    user_profile = os.environ.get("USERPROFILE", str(pathlib.Path.home()))
    theotown_dir_env = os.environ.get("THEOTOWN_DATA_DIR")

    if theotown_dir_env:
        theotown_dir = pathlib.Path(theotown_dir_env)
    else:
        theotown_dir = pathlib.Path(user_profile) / "TheoTown"

    prefs_dir = pathlib.Path(user_profile) / ".prefs" / "theotown"
    probe_plugin_dir = theotown_dir / "plugins" / "theotown_mcp_probe"

    return theotown_dir, prefs_dir, probe_plugin_dir


def compute_ssp_desktop_filename(name: str) -> str:
    """
    Computes the secure filename used by TheoTown's SSP (Secure SharedPreferences) on Desktop.
    Reverse engineered from info.flowersoft.theotown.util.SSP bytecode:
    token on Desktop is '::'. Hash is MD5(token + name), encoded as URL-safe Base64 (+ -> -, / -> _).
    """
    token = "::" + name
    md5_digest = hashlib.md5(token.encode("utf-8")).digest()
    b64 = base64.b64encode(md5_digest).decode("ascii")
    return b64.replace("/", "_").replace("+", "-")


class ProbeVerificationResult:
    def __init__(self):
        self.status = "PENDING"
        self.start_time = time.time()
        self.duration_seconds = 0.0
        self.checks: Dict[str, Dict[str, Any]] = {}
        self.errors: List[str] = []

    def record_check(self, check_name: str, passed: bool, details: Dict[str, Any], error: Optional[str] = None):
        self.checks[check_name] = {
            "passed": passed,
            "details": details,
            "error": error
        }
        if not passed and error:
            self.errors.append(f"[{check_name}] {error}")

    def finalize(self) -> bool:
        self.duration_seconds = round(time.time() - self.start_time, 3)
        all_passed = all(c["passed"] for c in self.checks.values()) and len(self.errors) == 0
        self.status = "PASS" if all_passed else "FAIL"
        return all_passed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "checks": self.checks,
            "errors": self.errors
        }


def verify_pmodext_storage(
    theotown_dir: pathlib.Path,
    expected_canary: str,
    strict_canary: bool = True
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Step 1: Inspects C:\\Users\\dmn05\\TheoTown\\.pmodext and parses the # JSON payload.
    Verifies that .pmodext exists, parses header metadata, and validates the canary token.
    """
    pmodext_path = theotown_dir / ".pmodext"
    details: Dict[str, Any] = {
        "path": str(pmodext_path),
        "exists": False,
        "size_bytes": 0,
        "header_lines": [],
        "json_keys_found": [],
        "canary_verified": False
    }

    if not pmodext_path.exists():
        return False, details, f".pmodext does not exist at {pmodext_path}"

    details["exists"] = True
    details["size_bytes"] = pmodext_path.stat().st_size

    try:
        content = pmodext_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return False, details, f"Failed to read .pmodext: {e}"

    lines = content.splitlines()
    header_lines = [line.strip() for line in lines[:5] if line.strip()]
    details["header_lines"] = header_lines

    # Find the # marker containing the serialized Lua table
    hash_idx = content.find("#")
    if hash_idx == -1:
        return False, details, "Delimiter '#' not found in .pmodext"

    raw_json = content[hash_idx + 1:].strip()
    if not raw_json:
        return False, details, "Payload after '#' is empty in .pmodext"

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return False, details, f"Failed to parse JSON payload after '#' in .pmodext: {e}"

    if not isinstance(data, dict):
        return False, details, f"Expected JSON dict after '#', got {type(data).__name__}"

    details["json_keys_found"] = list(data.keys())

    # Check for canary token
    canary_val = data.get("theotown_mcp_canary")
    if canary_val is not None:
        details["canary_value"] = canary_val
        if canary_val == expected_canary:
            details["canary_verified"] = True
            return True, details, None
        else:
            err = f"Canary token mismatch: expected '{expected_canary}', found '{canary_val}'"
            return False, details, err

    if strict_canary:
        err = (
            f"Canary key 'theotown_mcp_canary' not found in .pmodext. "
            f"Keys present: {list(data.keys())}. Note: TheoTown writes .pmodext during city save, "
            f"pause, or game exit."
        )
        return False, details, err
    else:
        # Non-strict mode: valid format confirmed
        details["format_valid"] = True
        return True, details, None


def verify_prefs_storage(prefs_dir: pathlib.Path) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Step 2: Inspects C:\\Users\\dmn05\\.prefs\\theotown\\ for storage artifacts.
    Verifies that the preference directory exists and contains expected preference files,
    including the hashed SSP file for global_transition_variables.
    """
    expected_gtv_file = compute_ssp_desktop_filename("global_transition_variables")
    details: Dict[str, Any] = {
        "prefs_dir": str(prefs_dir),
        "exists": False,
        "total_files": 0,
        "gtv_file_expected": expected_gtv_file,
        "gtv_file_found": False,
        "gtv_file_size": 0,
        "discovered_files": []
    }

    if not prefs_dir.exists() or not prefs_dir.is_dir():
        return False, details, f"Preferences directory does not exist: {prefs_dir}"

    details["exists"] = True
    files = os.listdir(prefs_dir)
    details["total_files"] = len(files)
    details["discovered_files"] = sorted(files)

    gtv_path = prefs_dir / expected_gtv_file
    if gtv_path.exists() and gtv_path.is_file():
        details["gtv_file_found"] = True
        details["gtv_file_size"] = gtv_path.stat().st_size
    else:
        return False, details, f"Expected SSP file for global_transition_variables ({expected_gtv_file}) not found"

    # Verify basic XML structure of the GTV preference file
    try:
        content = gtv_path.read_text(encoding="utf-8", errors="ignore")
        if "<properties>" not in content or "</properties>" not in content:
            return False, details, f"Corrupted XML structure in GTV preference file: {gtv_path}"
    except Exception as e:
        return False, details, f"Failed to inspect GTV preference file: {e}"

    return True, details, None


def write_atomic_lua(target_file: pathlib.Path, content: str, max_retries: int = 5) -> None:
    """
    Hardened Windows atomic file write:
    1. Writes to temporary file in the same directory (same NTFS volume).
    2. Flushes user buffer and fsyncs to physical storage.
    3. Closes file descriptor before renaming to avoid WinError 32 sharing violation.
    4. Executes os.replace with exponential backoff retry loop.
    """
    target_dir = target_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    prefix = f".tmp_{target_file.stem}_"
    tmp_fd, tmp_path_str = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=str(target_dir))
    tmp_path = pathlib.Path(tmp_path_str)

    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    delay = 0.05
    last_error = None
    for attempt in range(max_retries):
        try:
            os.replace(tmp_path, target_file)
            return
        except PermissionError as pe:
            last_error = pe
            time.sleep(delay)
            delay *= 2.0
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise e

    if tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
    raise PermissionError(f"Failed to replace {target_file} after {max_retries} attempts: {last_error}")


def verify_inbox_atomic_reload_and_handoff(
    probe_plugin_dir: pathlib.Path,
    handoff_token: str,
    timeout_seconds: float = 15.0,
    poll_interval: float = 0.25
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Step 3: Tests atomic writing to probe_inbox.lua (same-dir temp file + os.replace),
    waits for #LuaWrapper reload, and verifies that probe_core.lua logs/records the handoff token.
    Checks both probe_handoff_receipt.json and probe_core_handoff.json.
    """
    inbox_lua = probe_plugin_dir / "probe_inbox.lua"
    ack_json = probe_plugin_dir / "probe_inbox_ack.json"
    receipt_json = probe_plugin_dir / "probe_handoff_receipt.json"
    core_handoff_json = probe_plugin_dir / "probe_core_handoff.json"

    details: Dict[str, Any] = {
        "inbox_lua_path": str(inbox_lua),
        "ack_json_path": str(ack_json),
        "receipt_json_path": str(receipt_json),
        "core_handoff_json_path": str(core_handoff_json),
        "handoff_token_sent": handoff_token,
        "write_success": False,
        "inbox_reloaded": False,
        "core_handoff_received": False,
        "latency_ms": 0.0
    }

    # Clean prior acknowledgment files to guarantee fresh observation
    for f in [ack_json, receipt_json, core_handoff_json]:
        if f.exists():
            f.unlink(missing_ok=True)

    # Construct the inbox.lua hot-reload payload
    payload = f"""-- probe_inbox.lua: Generated by verify_r1_probe.py
local script = {{}}

local storage = TheoTown.getStorage()
local token = "{handoff_token}"
if storage then
    storage.theotown_mcp_handoff = token
    storage.theotown_mcp_handoff_timestamp = os.time()
end

-- Direct acknowledgment from inbox execution
Runtime.saveText("probe_inbox_ack.json", Runtime.toJson({{
    token = token,
    reloaded_at = os.time(),
    status = "INBOX_RELOAD_SUCCESS"
}}))

function script:init()
    local storage = TheoTown.getStorage()
    local token = "{handoff_token}"
    if storage then
        storage.theotown_mcp_handoff = token
        storage.theotown_mcp_handoff_timestamp = os.time()
    end
end

return script
"""

    write_start = time.time()
    try:
        write_atomic_lua(inbox_lua, payload)
        details["write_success"] = True
    except Exception as e:
        return False, details, f"Atomic write to probe_inbox.lua failed: {e}"

    # Poll for hot-reload and cross-script handoff
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        # Check inbox ack
        if not details["inbox_reloaded"] and ack_json.exists():
            try:
                ack_data = json.loads(ack_json.read_text(encoding="utf-8"))
                if ack_data.get("token") == handoff_token:
                    details["inbox_reloaded"] = True
                    details["latency_ms"] = round((time.time() - write_start) * 1000, 2)
            except Exception:
                pass

        # Check receipt or core listener handoff
        if receipt_json.exists():
            try:
                receipt_data = json.loads(receipt_json.read_text(encoding="utf-8"))
                if receipt_data.get("handoff_token") == handoff_token:
                    details["core_handoff_received"] = True
                    details["core_details"] = receipt_data
                    return True, details, None
            except Exception:
                pass

        if core_handoff_json.exists():
            try:
                core_data = json.loads(core_handoff_json.read_text(encoding="utf-8"))
                if core_data.get("received_token") == handoff_token:
                    details["core_handoff_received"] = True
                    details["core_details"] = core_data
                    return True, details, None
            except Exception:
                pass

        time.sleep(poll_interval)

    # Build actionable error message on timeout
    if not details["inbox_reloaded"]:
        err = (
            f"Timeout ({timeout_seconds}s) waiting for TheoTown #LuaWrapper to reload probe_inbox.lua. "
            f"Ensure TheoTown is running with the probe plugin installed and a city loaded."
        )
    else:
        err = (
            f"Inbox reloaded successfully, but probe_core.lua did not observe the handoff token "
            f"via TheoTown.getStorage() within {timeout_seconds}s."
        )

    return False, details, err


def verify_telemetry_schema(
    probe_plugin_dir: pathlib.Path,
    freshness_max_seconds: float = 120.0
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Step 4: Reads and validates probe_telemetry.json.
    Verifies city name, money, people/population, happiness, dimensions (width, height), speed, and freshness.
    """
    telemetry_path = probe_plugin_dir / "probe_telemetry.json"
    details: Dict[str, Any] = {
        "telemetry_path": str(telemetry_path),
        "exists": False,
        "fields_validated": {}
    }

    if not telemetry_path.exists():
        return False, details, f"Telemetry file does not exist at {telemetry_path}"

    details["exists"] = True

    try:
        data = json.loads(telemetry_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, details, f"Failed to parse probe_telemetry.json: {e}"

    if not isinstance(data, dict):
        return False, details, f"Telemetry root must be JSON object, got {type(data).__name__}"

    details["raw_payload"] = data

    # Schema specifications and boundary checks
    # 1. City Name
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return False, details, f"Field 'name' must be a non-empty string, got {repr(name)}"
    details["fields_validated"]["name"] = name

    # 2. Money / Budget (can be positive, zero, or negative in debt)
    money = data.get("money")
    if not isinstance(money, (int, float)):
        return False, details, f"Field 'money' must be numeric, got {repr(money)}"
    details["fields_validated"]["money"] = int(money)

    # 3. People / Population (City.getPeople() >= 0)
    people = data.get("people") if data.get("people") is not None else data.get("population")
    if not isinstance(people, (int, float)) or people < 0:
        return False, details, f"Field 'people' or 'population' must be a non-negative integer, got {repr(people)}"
    details["fields_validated"]["people"] = int(people)
    details["fields_validated"]["population"] = int(people)

    # 4. Happiness (0.0 to 1.0)
    happiness = data.get("happiness")
    if not isinstance(happiness, (int, float)) or not (0.0 <= happiness <= 1.0):
        return False, details, f"Field 'happiness' must be float in [0.0, 1.0], got {repr(happiness)}"
    details["fields_validated"]["happiness"] = float(happiness)

    # 5. Dimensions: width & height (> 0)
    width = data.get("width")
    height = data.get("height")
    if not isinstance(width, int) or width <= 0 or not isinstance(height, int) or height <= 0:
        return False, details, f"Dimensions width and height must be positive integers, got ({width}, {height})"
    details["fields_validated"]["dimensions"] = [width, height]

    # 6. Speed (0, 1, 2, 3, 4)
    speed = data.get("speed")
    if speed not in [0, 1, 2, 3, 4]:
        return False, details, f"Field 'speed' must be an integer in [0, 1, 2, 3, 4], got {repr(speed)}"
    details["fields_validated"]["speed"] = speed

    # 7. Freshness check
    timestamp = data.get("timestamp")
    if isinstance(timestamp, (int, float)):
        age = abs(time.time() - timestamp)
        details["fields_validated"]["telemetry_age_seconds"] = round(age, 1)
        if age > freshness_max_seconds:
            details["freshness_warning"] = f"Telemetry is {age:.1f}s old (exceeds {freshness_max_seconds}s threshold)"

    return True, details, None


def run_full_probe(
    theotown_dir: pathlib.Path,
    prefs_dir: pathlib.Path,
    probe_plugin_dir: pathlib.Path,
    canary_token: str,
    handoff_token: str,
    timeout: float,
    skip_hotreload: bool = False,
    strict_canary: bool = True
) -> ProbeVerificationResult:
    """Executes all verification steps and aggregates results."""
    res = ProbeVerificationResult()

    print("=" * 80)
    print(" THEOTOWN MCP SERVER — PHASE 0 IPC & TELEMETRY GROUND-TRUTH VERIFICATION PROBE")
    print("=" * 80)
    print(f"TheoTown Data Dir:  {theotown_dir}")
    print(f"Preferences Dir:    {prefs_dir}")
    print(f"Probe Plugin Dir:   {probe_plugin_dir}")
    print(f"Expected Canary:    {canary_token}")
    print(f"Handoff Token:      {handoff_token}")
    print("-" * 80)

    # Step 1: .pmodext inspection
    print("\n[Step 1/4] Inspecting .pmodext file storage...")
    p_ok, p_det, p_err = verify_pmodext_storage(theotown_dir, canary_token, strict_canary=strict_canary)
    res.record_check("pmodext_storage", p_ok, p_det, p_err)
    if p_ok:
        print(f"  [PASS] .pmodext inspected successfully ({p_det['size_bytes']} bytes).")
        print(f"         Canary verified: {p_det.get('canary_verified')}")
        print(f"         JSON keys found: {p_det.get('json_keys_found')}")
    else:
        print(f"  [FAIL] .pmodext check failed: {p_err}")

    # Step 2: .prefs\\theotown inspection
    print("\n[Step 2/4] Inspecting .prefs\\theotown preference artifacts...")
    pr_ok, pr_det, pr_err = verify_prefs_storage(prefs_dir)
    res.record_check("prefs_storage", pr_ok, pr_det, pr_err)
    if pr_ok:
        print(f"  [PASS] Preferences verified ({pr_det['total_files']} files).")
        print(f"         GTV artifact found: {pr_det['gtv_file_expected']} ({pr_det['gtv_file_size']} bytes)")
    else:
        print(f"  [FAIL] Preferences check failed: {pr_err}")

    # Step 3: Atomic write & hot-reload handoff
    if not skip_hotreload:
        print(f"\n[Step 3/4] Testing atomic write to probe_inbox.lua and #LuaWrapper reload...")
        h_ok, h_det, h_err = verify_inbox_atomic_reload_and_handoff(
            probe_plugin_dir, handoff_token, timeout_seconds=timeout
        )
        res.record_check("inbox_hotreload_handoff", h_ok, h_det, h_err)
        if h_ok:
            print(f"  [PASS] Atomic write & reload handoff successful!")
            print(f"         Reload latency: {h_det['latency_ms']} ms")
            print(f"         Core listener handoff confirmed via TheoTown.getStorage().")
        else:
            print(f"  [FAIL] Hot-reload handoff check failed: {h_err}")
    else:
        print("\n[Step 3/4] Skipped hot-reload check as requested (--skip-hotreload).")

    # Step 4: Telemetry schema validation
    if not skip_hotreload:
        print(f"\n[Step 4/4] Validating probe_telemetry.json city state...")
        t_ok, t_det, t_err = verify_telemetry_schema(probe_plugin_dir)
        res.record_check("telemetry_validation", t_ok, t_det, t_err)
        if t_ok:
            vals = t_det["fields_validated"]
            print(f"  [PASS] Telemetry schema validated cleanly.")
            print(f"         City: '{vals['name']}', Pop: {vals['people']}, Money: ${vals['money']}")
            print(f"         Happiness: {vals['happiness']:.2f}, Size: {vals['dimensions'][0]}x{vals['dimensions'][1]}, Speed: {vals['speed']}")
        else:
            print(f"  [FAIL] Telemetry validation failed: {t_err}")

    res.finalize()
    print("\n" + "=" * 80)
    print(f" FINAL PROBE RESULT: {res.status} (Completed in {res.duration_seconds}s)")
    if res.errors:
        print(" Errors:")
        for err in res.errors:
            print(f"   - {err}")
    print("=" * 80)

    return res


def main():
    parser = argparse.ArgumentParser(
        description="TheoTown MCP Server — Phase 0 IPC & Telemetry Ground-Truth Verification Probe"
    )
    def_tt, def_prefs, def_probe = get_default_paths()

    parser.add_argument("--data-dir", type=pathlib.Path, default=def_tt, help="TheoTown user data directory")
    parser.add_argument("--prefs-dir", type=pathlib.Path, default=def_prefs, help="TheoTown .prefs directory")
    parser.add_argument("--probe-dir", type=pathlib.Path, default=def_probe, help="Path to theotown_mcp_probe plugin")
    parser.add_argument("--canary-token", type=str, default=DEFAULT_CANARY_TOKEN, help="Expected canary token")
    parser.add_argument("--handoff-token", type=str, default=f"HANDOFF_{int(time.time())}", help="Handoff token")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout in seconds for hot-reload wait")
    parser.add_argument("--skip-hotreload", action="store_true", help="Skip hotreload and telemetry check")
    parser.add_argument("--non-strict-canary", action="store_true", help="Do not fail if canary key is absent in .pmodext")
    parser.add_argument("--json-out", type=pathlib.Path, default=None, help="Save structured report to JSON file")

    args = parser.parse_args()

    result = run_full_probe(
        theotown_dir=args.data_dir,
        prefs_dir=args.prefs_dir,
        probe_plugin_dir=args.probe_dir,
        canary_token=args.canary_token,
        handoff_token=args.handoff_token,
        timeout=args.timeout,
        skip_hotreload=args.skip_hotreload,
        strict_canary=not args.non_strict_canary
    )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"\nStructured result written to: {args.json_out}")

    if result.status == "PASS":
        sys.exit(EXIT_SUCCESS)
    else:
        if any("Timeout" in err or "does not exist" in err for err in result.errors):
            sys.exit(EXIT_TIMEOUT_OR_NOT_READY)
        else:
            sys.exit(EXIT_ASSERTION_FAILURE)


if __name__ == "__main__":
    main()
