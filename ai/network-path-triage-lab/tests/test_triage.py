import unittest
from triage import PHASES, diagnose

NOW = "2026-09-29T04:00:00Z"


def sample(results=None):
    results = results or {}
    return {"probes": [{"phase": p, "result": results.get(p, "PASS"), "observed_at": NOW} for p in PHASES]}


class TriageTests(unittest.TestCase):
    def test_healthy(self):
        self.assertEqual(diagnose(sample(), NOW)["status"], "HEALTHY")

    def test_first_fault_precedes_downstream_symptoms(self):
        result = diagnose(sample({"endpoint": "FAIL", "mesh": "FAIL", "application": "FAIL"}), NOW)
        self.assertEqual(result["first_fault_candidate"], "endpoint")
        self.assertEqual(result["downstream_failures"], ["mesh", "application"])

    def test_unknown_before_failure_prevents_false_root_cause(self):
        result = diagnose(sample({"dns": "UNKNOWN", "policy": "FAIL"}), NOW)
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["first_fault_candidate"])

    def test_stale_evidence_fails_closed(self):
        case = sample()
        case["probes"][0]["observed_at"] = "2026-09-29T03:54:59Z"
        with self.assertRaisesRegex(ValueError, "stale"):
            diagnose(case, NOW)

    def test_duplicate_and_missing_phases_fail(self):
        case = sample()
        case["probes"][-1]["phase"] = "dns"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            diagnose(case, NOW)

    def test_deterministic_evidence_hash(self):
        self.assertEqual(diagnose(sample(), NOW)["evidence_sha256"], diagnose(sample(), NOW)["evidence_sha256"])

    def test_probe_timestamp_is_bound_to_evidence_hash(self):
        changed = sample()
        changed["probes"][0]["observed_at"] = "2026-09-29T03:59:59Z"
        self.assertNotEqual(diagnose(sample(), NOW)["evidence_sha256"], diagnose(changed, NOW)["evidence_sha256"])

    def test_future_evidence_fails(self):
        case = sample()
        case["probes"][0]["observed_at"] = "2026-09-29T04:00:01Z"
        with self.assertRaisesRegex(ValueError, "future"):
            diagnose(case, NOW)


if __name__ == "__main__":
    unittest.main()
