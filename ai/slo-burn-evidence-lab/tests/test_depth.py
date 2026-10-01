import unittest

from burnlab import assess
from test_burn import NOW, fixture


class ExactBurnTests(unittest.TestCase):
    def test_high_precision_objective_crosses_threshold_only_exactly(self):
        data = fixture()
        data["objective"] = "0." + "9" * 36
        for bucket in data["buckets"]:
            bucket["total"] = 10**40
        for bucket in data["buckets"][-12:]:
            bucket["failed"] = 143999
        result = assess(data, now=NOW)
        self.assertEqual(result["windows"]["5m"]["burn"], "14.400")
        self.assertEqual(result["decision"], "NO_PAGE")
        for bucket in data["buckets"][-12:]:
            bucket["failed"] = 144000
        self.assertTrue(assess(data, now=NOW)["fast_burn"])

    def test_prefix_windows_match_direct_count_oracle(self):
        data = fixture()
        for index, bucket in enumerate(data["buckets"]):
            bucket["total"] = 1000 + index
            bucket["failed"] = index % 7
        result = assess(data, now=NOW)
        for name, count in (("5m", 1), ("30m", 6), ("1h", 12), ("6h", 72)):
            self.assertEqual(
                result["windows"][name]["total"],
                sum(row["total"] for row in data["buckets"][-count:]),
            )
            self.assertEqual(
                result["windows"][name]["failed"],
                sum(row["failed"] for row in data["buckets"][-count:]),
            )
