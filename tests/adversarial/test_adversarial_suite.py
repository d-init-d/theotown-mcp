"""
Adversarial Stress-Testing Suite for verify_r1_probe.py
Authored by Challenger 2 (Milestone M0)

Tests:
1. .pmodext parser edge cases (missing '#', malformed JSON, empty file, extra '#' chars, non-dict payloads, binary data, etc.)
2. Desktop SSP MD5 Base64 hashing against live TheoTown preferences, character replacements (+ -> -, / -> _), edge cases.
"""

import base64
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

# Import target functions from tools/probe/verify_r1_probe.py
PROBE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "tools" / "probe"
sys.path.insert(0, str(PROBE_DIR))

from verify_r1_probe import compute_ssp_desktop_filename, verify_pmodext_storage


class TestPmodextParserAdversarial(unittest.TestCase):
    """Adversarial stress tests for verify_pmodext_storage()."""

    def setUp(self):
        self.test_dir = pathlib.Path(tempfile.mkdtemp(prefix="tt_pmodext_test_"))
        self.canary = "TEST_CANARY_TOKEN_XYZ_123"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write_pmodext(self, content: str, encoding: str = "utf-8"):
        pmodext_path = self.test_dir / ".pmodext"
        pmodext_path.write_text(content, encoding=encoding)
        return pmodext_path

    def _write_pmodext_bytes(self, content: bytes):
        pmodext_path = self.test_dir / ".pmodext"
        pmodext_path.write_bytes(content)
        return pmodext_path

    # --- Test Category A: Missing '#' Delimiter ---
    def test_missing_hash_in_header_only_file(self):
        """File with headers but no '#' delimiter."""
        content = "Last played: 1789199218075\nAccess token: 9883cb42740462ce64a542ee1709d309\n"
        self._write_pmodext(content)
        ok, details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Delimiter '#' not found", err)
        self.assertTrue(details["exists"])

    def test_missing_hash_in_empty_file(self):
        """0-byte .pmodext file."""
        self._write_pmodext("")
        ok, details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Delimiter '#' not found", err)
        self.assertEqual(details["size_bytes"], 0)

    def test_missing_hash_in_plain_text(self):
        """File with non-TheoTown plain text."""
        self._write_pmodext("Hello world, this is a plain text file without delimiters.")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Delimiter '#' not found", err)

    # --- Test Category B: Empty or Whitespace-Only Payload after '#' ---
    def test_hash_with_empty_payload(self):
        """File ending immediately at '#'."""
        self._write_pmodext("Header\n#")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Payload after '#' is empty", err)

    def test_hash_with_whitespace_only_payload(self):
        """File with spaces and newlines after '#'."""
        self._write_pmodext("Header\n#   \n\n\t  \n")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Payload after '#' is empty", err)

    # --- Test Category C: Malformed JSON after '#' ---
    def test_malformed_json_unclosed_brace(self):
        """Payload has invalid unclosed JSON."""
        self._write_pmodext('Header\n#{"theotown_mcp_canary": "foo"')
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Failed to parse JSON payload", err)

    def test_malformed_json_random_gibberish(self):
        """Payload contains arbitrary non-JSON string."""
        self._write_pmodext("Header\n#this_is_not_json:123")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Failed to parse JSON payload", err)

    def test_json_list_instead_of_dict(self):
        """Payload is a JSON array instead of an object."""
        self._write_pmodext('Header\n#["item1", "item2", "item3"]')
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Expected JSON dict after '#', got list", err)

    def test_json_primitive_string(self):
        """Payload is a JSON primitive string."""
        self._write_pmodext('Header\n#"just a string"')
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Expected JSON dict after '#', got str", err)

    def test_json_primitive_number(self):
        """Payload is a JSON number."""
        self._write_pmodext('Header\n#123456')
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Expected JSON dict after '#', got int", err)

    def test_json_primitive_boolean(self):
        """Payload is a JSON boolean."""
        self._write_pmodext('Header\n#true')
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Expected JSON dict after '#', got bool", err)

    def test_json_null(self):
        """Payload is JSON null."""
        self._write_pmodext('Header\n#null')
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Expected JSON dict after '#', got NoneType", err)

    # --- Test Category D: Extra '#' Characters ---
    def test_hash_inside_json_string_value(self):
        """JSON value itself contains '#' characters (e.g. canary with '#')."""
        canary_with_hash = "TOKEN#WITH#MULTIPLE#HASHES"
        payload = json.dumps({
            "theotown_mcp_canary": canary_with_hash,
            "comment": "Color is #FF00AA and hashtag is #theotown"
        })
        self._write_pmodext(f"Last played: 123\nAccess token: abc\n\n\n#{payload}\n")
        ok, details, err = verify_pmodext_storage(self.test_dir, canary_with_hash)
        self.assertTrue(ok, f"Should pass when '#' is inside JSON string, err: {err}")
        self.assertTrue(details["canary_verified"])
        self.assertEqual(details["canary_value"], canary_with_hash)

    def test_hash_inside_json_keys(self):
        """JSON key contains '#' character."""
        payload = json.dumps({
            "key#1": "val1",
            "theotown_mcp_canary": self.canary
        })
        self._write_pmodext(f"Header\n#{payload}")
        ok, details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertTrue(ok, f"Should pass when '#' is in JSON key, err: {err}")
        self.assertIn("key#1", details["json_keys_found"])

    def test_hash_in_header_before_payload(self):
        """
        ADVERSARIAL CHALLENGE:
        What happens if the header text contains a '#' before the actual JSON payload?
        E.g., '# Comment line' or 'Access token: abc#123'
        content.find('#') finds the FIRST '#', causing the parser to treat
        the rest of the header + payload as the JSON payload!
        """
        payload = json.dumps({"theotown_mcp_canary": self.canary})
        adversarial_content = f"# Comment in header\nLast played: 123\nAccess token: abc\n#{payload}\n"
        self._write_pmodext(adversarial_content)
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        # Note: In TheoTown bytecode:
        # GTV.load() also uses `indexOf('#')`, so TheoTown itself would fail if header contained '#'.
        # However, verifying how our parser behaves:
        self.assertFalse(ok)
        self.assertIn("Failed to parse JSON payload", err)

    def test_multiple_hashes_consecutive(self):
        """Consecutive '#' markers (e.g. '##{...}')."""
        payload = json.dumps({"theotown_mcp_canary": self.canary})
        self._write_pmodext(f"Header\n##{payload}")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertFalse(ok)
        self.assertIn("Failed to parse JSON payload", err)

    def test_multiple_hash_payload_lines(self):
        """File containing two separate '#{...}' lines."""
        payload1 = json.dumps({"old_data": 1})
        payload2 = json.dumps({"theotown_mcp_canary": self.canary})
        self._write_pmodext(f"Header\n#{payload1}\n#{payload2}")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary)
        # Two consecutive JSON payloads concatenated with newline is invalid single JSON
        self.assertFalse(ok)
        self.assertIn("Failed to parse JSON payload", err)

    # --- Test Category E: Canary Matching & Strictness Modes ---
    def test_canary_match_strict_and_non_strict(self):
        """Canary exactly matches."""
        payload = json.dumps({"theotown_mcp_canary": self.canary, "other_var": 42})
        self._write_pmodext(f"Header\n#{payload}")
        
        ok_strict, det_s, err_s = verify_pmodext_storage(self.test_dir, self.canary, strict_canary=True)
        self.assertTrue(ok_strict)
        self.assertIsNone(err_s)
        self.assertTrue(det_s["canary_verified"])

        ok_nonstrict, det_ns, err_ns = verify_pmodext_storage(self.test_dir, self.canary, strict_canary=False)
        self.assertTrue(ok_nonstrict)
        self.assertIsNone(err_ns)
        self.assertTrue(det_ns["canary_verified"])

    def test_canary_mismatch(self):
        """Canary key is present but value differs."""
        payload = json.dumps({"theotown_mcp_canary": "WRONG_TOKEN"})
        self._write_pmodext(f"Header\n#{payload}")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary, strict_canary=True)
        self.assertFalse(ok)
        self.assertIn("Canary token mismatch", err)

    def test_canary_absent_strict_fails(self):
        """Canary key is missing in strict mode."""
        payload = json.dumps({"some_unrelated_key": True})
        self._write_pmodext(f"Header\n#{payload}")
        ok, _details, err = verify_pmodext_storage(self.test_dir, self.canary, strict_canary=True)
        self.assertFalse(ok)
        self.assertIn("Canary key 'theotown_mcp_canary' not found", err)

    def test_canary_absent_non_strict_passes(self):
        """Canary key is missing in non-strict mode (format confirmation)."""
        payload = json.dumps({"some_unrelated_key": True})
        self._write_pmodext(f"Header\n#{payload}")
        ok, details, err = verify_pmodext_storage(self.test_dir, self.canary, strict_canary=False)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertTrue(details["format_valid"])
        self.assertFalse(details["canary_verified"])

    # --- Test Category F: Large File Stress & Padding ---
    def test_live_theotown_exact_structure(self):
        """Emulates exact TheoTown .pmodext structure with 959 empty lines."""
        lines = [
            "Last played: 1789199218075",
            "Access token: 9883cb42740462ce64a542ee1709d309"
        ]
        lines.extend([""] * 959)
        payload = json.dumps({"theotown_mcp_canary": self.canary, "dOrFeEgVFK71f54k": False})
        lines.append(f"#{payload}")
        content = "\n".join(lines)
        self._write_pmodext(content)

        ok, details, _err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertTrue(ok)
        self.assertEqual(len(details["header_lines"]), 2)
        self.assertTrue(details["canary_verified"])

    def test_massive_file_stress_100k_lines(self):
        """Stress tests with 100,000 empty lines."""
        lines = ["Header 1", "Header 2"]
        lines.extend([""] * 100_000)
        payload = json.dumps({"theotown_mcp_canary": self.canary})
        lines.append(f"#{payload}")
        content = "\n".join(lines)
        self._write_pmodext(content)

        ok, details, _err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertTrue(ok)
        self.assertTrue(details["canary_verified"])

    # --- Test Category G: Binary / Unicode / Missing File ---
    def test_binary_garbage_before_hash(self):
        """Binary data before '#' with utf-8 errors=ignore handling."""
        header_bytes = b"\x00\xff\xfe\x80\x90Header line\n\x00\x01\n"
        payload = json.dumps({"theotown_mcp_canary": self.canary}).encode("utf-8")
        self._write_pmodext_bytes(header_bytes + b"#" + payload)

        ok, details, err = verify_pmodext_storage(self.test_dir, self.canary)
        self.assertTrue(ok, f"Binary header should be tolerated via errors='ignore': {err}")
        self.assertTrue(details["canary_verified"])

    def test_unicode_canary_token(self):
        """Canary token with diverse international Unicode characters."""
        unicode_canary = "CANARY_ThànhPhố_TheoTown_2026_🔥_日本語"
        payload = json.dumps({"theotown_mcp_canary": unicode_canary}, ensure_ascii=False)
        self._write_pmodext(f"Header\n#{payload}")

        ok, details, err = verify_pmodext_storage(self.test_dir, unicode_canary)
        self.assertTrue(ok, f"Unicode canary failed: {err}")
        self.assertEqual(details["canary_value"], unicode_canary)

    def test_nonexistent_directory(self):
        """Target file does not exist."""
        nonexistent = self.test_dir / "nonexistent_subdir"
        ok, details, err = verify_pmodext_storage(nonexistent, self.canary)
        self.assertFalse(ok)
        self.assertFalse(details["exists"])
        self.assertIn("does not exist", err)


class TestDesktopSSPHashingAdversarial(unittest.TestCase):
    """Adversarial stress tests for compute_ssp_desktop_filename()."""

    def test_ground_truth_known_preference_names(self):
        """Verifies compute_ssp_desktop_filename against verified TheoTown preference names."""
        known_cases = {
            "global_transition_variables": "LSsdSvElX2ZethqZnh4DBg==",
            "analytics": "1URVs0HNCC8P02EpNmnWIg==",
            "dynamic_config_file": "6XX_0OnqyQpCklLcCP3_EA==",
            "user_store": "J4ZfipI_h5Lg4ScnbXfyEA==",
            "localplugins": "VTnCwJh648no6sWWv2siNQ==",
            "newcontent": "dD_zGxpjhkuyQqo3tladNw==",
            "session": "vtMSJBR25mn1paUeRZEYlg=="
        }
        for pref_name, expected_hash in known_cases.items():
            computed = compute_ssp_desktop_filename(pref_name)
            self.assertEqual(
                computed, expected_hash,
                f"Mismatch for '{pref_name}': expected {expected_hash}, got {computed}"
            )

    def test_ssp_internal_xml_entry_key_derivation(self):
        """Verifies internal XML entry key formula: compute_ssp(name + ':data')."""
        # Verify global_transition_variables:data
        gtv_entry = compute_ssp_desktop_filename("global_transition_variables:data")
        self.assertEqual(gtv_entry, "wrL8ZE2gsOxFNm0ByOdukg==")

    def test_urlsafe_base64_replacement_slash_to_underscore(self):
        """Tests that '/' in standard Base64 is strictly replaced with '_'."""
        # Find an input string where standard Base64(MD5("::" + s)) contains '/'
        # We search deterministically:
        found = False
        for i in range(1000):
            cand = f"test_candidate_slash_{i}"
            raw_b64 = base64.b64encode(hashlib.md5(("::" + cand).encode("utf-8")).digest()).decode("ascii")
            if "/" in raw_b64:
                computed = compute_ssp_desktop_filename(cand)
                self.assertNotIn("/", computed)
                self.assertIn("_", computed)
                self.assertEqual(computed, raw_b64.replace("/", "_").replace("+", "-"))
                found = True
                break
        self.assertTrue(found, "Should find candidate triggering '/' -> '_' replacement")

    def test_urlsafe_base64_replacement_plus_to_dash(self):
        """Tests that '+' in standard Base64 is strictly replaced with '-'."""
        found = False
        for i in range(1000):
            cand = f"test_candidate_plus_{i}"
            raw_b64 = base64.b64encode(hashlib.md5(("::" + cand).encode("utf-8")).digest()).decode("ascii")
            if "+" in raw_b64:
                computed = compute_ssp_desktop_filename(cand)
                self.assertNotIn("+", computed)
                self.assertIn("-", computed)
                self.assertEqual(computed, raw_b64.replace("/", "_").replace("+", "-"))
                found = True
                break
        self.assertTrue(found, "Should find candidate triggering '+' -> '-' replacement")

    def test_live_files_character_conformance(self):
        """Verifies that all 12 live SSP preference files adhere to the URL-safe Base64 charset."""
        prefs_dir = pathlib.Path(os.environ.get("USERPROFILE", "")) / ".prefs" / "theotown"
        if prefs_dir.exists():
            files = [f for f in os.listdir(prefs_dir) if f.endswith("==")]
            self.assertEqual(len(files), 12, "Expected exactly 12 SSP files in live .prefs/theotown")
            for f in files:
                self.assertEqual(len(f), 24, f"SSP filename {f} must be exactly 24 chars (MD5 Base64)")
                self.assertTrue(f.endswith("=="), f"SSP filename {f} must end with '==' padding")
                self.assertNotIn("/", f, f"SSP filename {f} must not contain '/'")
                self.assertNotIn("+", f, f"SSP filename {f} must not contain '+'")
                # Ensure characters are valid URL-safe Base64
                valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")
                self.assertTrue(set(f).issubset(valid_chars), f"Invalid characters in filename: {f}")

    def test_empty_string_input(self):
        """Tests behavior on empty preference name."""
        computed = compute_ssp_desktop_filename("")
        expected = base64.b64encode(hashlib.md5(b"::").digest()).decode("ascii").replace("/", "_").replace("+", "-")
        self.assertEqual(computed, expected)
        self.assertEqual(len(computed), 24)

    def test_unicode_preference_names(self):
        """Tests UTF-8 encoded preference names with special/international characters."""
        unicode_names = [
            "cidade_são_paulo",
            "도시_서울",
            "東京_とうきょう",
            "город_москва",
            "thành_phố_hồ_chí_minh"
        ]
        for uname in unicode_names:
            computed = compute_ssp_desktop_filename(uname)
            expected = base64.b64encode(hashlib.md5(("::" + uname).encode("utf-8")).digest()).decode("ascii").replace("/", "_").replace("+", "-")
            self.assertEqual(computed, expected)
            self.assertEqual(len(computed), 24)

    def test_idempotence_and_deterministic_output(self):
        """Tests that compute_ssp_desktop_filename is purely deterministic across 10,000 runs."""
        name = "global_transition_variables"
        expected = "LSsdSvElX2ZethqZnh4DBg=="
        for _ in range(10_000):
            self.assertEqual(compute_ssp_desktop_filename(name), expected)


def run_all_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPmodextParserAdversarial))
    suite.addTests(loader.loadTestsFromTestCase(TestDesktopSSPHashingAdversarial))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result


if __name__ == "__main__":
    res = run_all_tests()
    sys.exit(0 if res.wasSuccessful() else 1)
