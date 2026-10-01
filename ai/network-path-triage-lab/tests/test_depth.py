import unittest

from test_triage import NOW, sample
from triage import diagnose


class CanonicalProbeTests(unittest.TestCase):
    def test_equal_instants_offsets_and_input_order_share_hash(self):
        shifted = sample()
        shifted["probes"].reverse()
        for probe in shifted["probes"]:
            probe["observed_at"] = "2026-09-29T13:00:00+09:00"
        self.assertEqual(
            diagnose(shifted, "2026-09-29T13:00:00+09:00")["evidence_sha256"],
            diagnose(sample(), NOW)["evidence_sha256"],
        )

    def test_invalid_age_types_and_input_are_domain_errors(self):
        for value in (True, 1.5, "300", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                diagnose(sample(), NOW, value)
        with self.assertRaises(ValueError):
            diagnose([], NOW)

    def test_age_boundary_inclusive_and_one_second_after_rejects(self):
        data = sample()
        data["probes"][0]["observed_at"] = "2026-09-29T03:55:00Z"
        self.assertEqual(diagnose(data, NOW)["status"], "HEALTHY")
        with self.assertRaises(ValueError):
            diagnose(data, "2026-09-29T04:00:01Z")
