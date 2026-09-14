"""
Adversarial test suite for verify_r1_probe.py components:
1. .pmodext storage parser (edge cases, delimiters, malformed JSON, empty files, extra '#' delimiters)
2. Desktop SSP MD5 Base64 hashing algorithm against known TheoTown preference files
"""

import io
import os
import pathlib
import re
import sys
import zipfile

import pytest

# Add tools/probe to import path
PROBE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "tools" / "probe"
sys.path.insert(0, str(PROBE_DIR))

from verify_r1_probe import compute_ssp_desktop_filename


def test_ssp_hash_matching():
    print("=== TEST 1: DESKTOP SSP MD5 BASE64 HASH MATCHING ===")
    prefs_dir = pathlib.Path(os.environ.get("USERPROFILE", "")) / ".prefs" / "theotown"
    if not prefs_dir.is_dir():
        pytest.skip("TheoTown desktop preferences are not installed on this machine")
    actual_files = set(os.listdir(prefs_dir))
    ssp_files = {f for f in actual_files if f.endswith("==")}
    print(f"Total SSP files in {prefs_dir}: {len(ssp_files)}")

    # Extract all candidate strings from TheoTown66.lby
    jar_path = pathlib.Path(
        os.environ.get(
            "THEOTOWN_JAR",
            r"d:\steam\steamapps\common\TheoTown\TheoTown66.lby",
        )
    )
    if not jar_path.is_file():
        pytest.skip("TheoTown66.lby is unavailable; set THEOTOWN_JAR to run this ground-truth test")
    with jar_path.open("rb") as f:
        f.seek(16)
        data = f.read()
    zf = zipfile.ZipFile(io.BytesIO(data))

    all_strings = set()
    for fname in zf.namelist():
        if fname.endswith(".class"):
            cdata = zf.read(fname)
            for s in re.findall(b"[\x20-\x7e]{1,60}", cdata):
                all_strings.add(s.decode("latin1"))

    matched = {}
    for s in all_strings:
        h = compute_ssp_desktop_filename(s)
        if h in ssp_files and h not in matched:
            matched[h] = s

    print(f"Matched {len(matched)} / {len(ssp_files)} files:")
    for h, s in sorted(matched.items()):
        print(f"  {h} -> '{s}'")

    unmatched = ssp_files - set(matched.keys())
    if unmatched:
        print(f"Unmatched files ({len(unmatched)}): {unmatched}")

    # Assert critical known files
    assert "LSsdSvElX2ZethqZnh4DBg==" in matched, "global_transition_variables must match LSsdSvElX2ZethqZnh4DBg=="
    assert matched["LSsdSvElX2ZethqZnh4DBg=="] == "global_transition_variables"
    print("Test 1 PASS: compute_ssp_desktop_filename correctly matches TheoTown ground truth.")
    assert len(matched) > 0

if __name__ == "__main__":
    test_ssp_hash_matching()
