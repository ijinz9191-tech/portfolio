import copy
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from burnlab import BurnError, assess, assess_segments


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 29, 0, 1, tzinfo=timezone.utc)


def fixture(failed=0):
    start = datetime(2026, 9, 28, 18, 5, tzinfo=timezone.utc)
    return {"service": "checkout-synthetic", "objective": "0.999", "buckets": [
        {"end": (start + timedelta(minutes=5*i)).isoformat().replace("+00:00", "Z"), "total": 1000, "failed": failed}
        for i in range(72)]}


class BurnTests(unittest.TestCase):
    def test_sustained_fast_burn_pages_and_exposes_weighted_evidence(self):
        data = fixture()
        for bucket in data["buckets"][-12:]:
            bucket["failed"] = 20
        result = assess(data, now=NOW)
        self.assertEqual(result["decision"], "PAGE")
        self.assertTrue(result["fast_burn"])
        self.assertFalse(result["slow_burn"])
        self.assertEqual(result["windows"]["1h"]["failed"], 240)
        self.assertEqual(result["windows"]["1h"]["burn"], "20.000")

    def test_short_spike_without_long_window_burn_does_not_page(self):
        data = fixture()
        data["buckets"][-1]["failed"] = 20
        result = assess(data, now=NOW)
        self.assertEqual(result["decision"], "NO_PAGE")
        self.assertEqual(result["windows"]["5m"]["burn"], "20.000")

    def test_slow_burn_pages_without_fast_burn(self):
        data = fixture(7)
        result = assess(data, now=NOW)
        self.assertEqual(result["decision"], "PAGE")
        self.assertFalse(result["fast_burn"])
        self.assertTrue(result["slow_burn"])

    def test_zero_traffic_is_unknown_not_zero_error_evidence(self):
        data = fixture()
        for bucket in data["buckets"]:
            bucket["total"] = 0
        result = assess(data, now=NOW)
        self.assertEqual(result["decision"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["windows"]["6h"]["burn"])

    def test_zero_traffic_segment_keeps_aggregate_unknown(self):
        quiet = fixture()["buckets"]
        for bucket in quiet:
            bucket["total"] = 0
        result = assess_segments({"service": "checkout-synthetic", "objective": "0.999",
                                  "segments": {"active": fixture()["buckets"], "quiet": quiet}}, now=NOW)
        self.assertEqual(result["decision"], "INSUFFICIENT_DATA")
        self.assertEqual(result["segments"]["quiet"]["decision"], "INSUFFICIENT_DATA")

    def test_missing_or_stale_observations_reject(self):
        data = fixture()
        data["buckets"][50]["end"] = data["buckets"][49]["end"]
        with self.assertRaisesRegex(BurnError, "gap"):
            assess(data, now=NOW)
        with self.assertRaisesRegex(BurnError, "stale"):
            assess(fixture(), now=NOW + timedelta(minutes=10))

    def test_invalid_counts_and_objective_reject(self):
        data = fixture()
        data["buckets"][-1]["failed"] = 1001
        with self.assertRaisesRegex(BurnError, "counts"):
            assess(data, now=NOW)
        data = fixture()
        data["objective"] = True
        with self.assertRaisesRegex(BurnError, "objective"):
            assess(data, now=NOW)

    def test_evidence_hash_changes_when_count_changes(self):
        data = fixture()
        first = assess(data, now=NOW)["evidence_sha256"]
        data["buckets"][-1]["failed"] = 1
        self.assertNotEqual(assess(data, now=NOW)["evidence_sha256"], first)

    def test_display_rounding_does_not_cross_alert_threshold(self):
        data = fixture()
        for bucket in data["buckets"]:
            bucket["total"] = 10_000_000
        for bucket in data["buckets"][-12:]:
            bucket["failed"] = 143_999
        result = assess(data, now=NOW)
        self.assertEqual(result["windows"]["5m"]["burn"], "14.400")
        self.assertEqual(result["decision"], "NO_PAGE")

    def test_cli_reproduces_sample_and_rejects_stale_clock(self):
        command = [sys.executable, "-B", "-m", "burnlab", str(ROOT / "samples" / "sustained.json"), "--now", "2026-09-29T00:01:00Z"]
        ok = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["decision"], "PAGE")
        stale = subprocess.run(command[:-1] + ["2026-09-29T01:00:00Z"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(stale.returncode, 2)
        self.assertIn("REJECTED", stale.stderr)

    def test_segment_regression_pages_even_when_large_path_is_healthy(self):
        healthy = fixture()["buckets"]
        for bucket in healthy:
            bucket["total"] = 100_000
        failing = fixture()["buckets"]
        for bucket in failing[-12:]:
            bucket["failed"] = 20
        result = assess_segments({"service": "checkout-synthetic", "objective": "0.999",
                                  "segments": {"card": healthy, "bank-transfer": failing}}, now=NOW)
        self.assertEqual(result["decision"], "PAGE")
        self.assertEqual(result["paged_segments"], ["bank-transfer"])
        self.assertEqual(result["segments"]["card"]["decision"], "NO_PAGE")

    def test_segment_gap_rejects_entire_decision(self):
        failing = fixture()["buckets"]
        failing.pop()
        with self.assertRaisesRegex(BurnError, "72 to 288"):
            assess_segments({"service": "checkout-synthetic", "objective": "0.999",
                             "segments": {"card": fixture()["buckets"], "bank-transfer": failing}}, now=NOW)

    def test_segment_service_name_is_validated(self):
        with self.assertRaisesRegex(BurnError, "service"):
            assess_segments({"service": 42, "objective": "0.999",
                             "segments": {"card": fixture()["buckets"], "transfer": fixture()["buckets"]}}, now=NOW)


if __name__ == "__main__":
    unittest.main()
