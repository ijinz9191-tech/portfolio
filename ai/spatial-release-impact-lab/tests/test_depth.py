import copy
import random
import unittest

from audit import audit


class InverseImpactTests(unittest.TestCase):
    def test_inverse_index_matches_full_path_scan_oracle(self):
        generator = random.Random(303)
        segments = [{"id": f"s{i}", "geometry_revision": "v1"} for i in range(50)]
        routes = [
            {
                "id": f"r{i:03}",
                "segment_ids": generator.sample([row["id"] for row in segments], 20),
            }
            for i in range(200)
        ]
        baseline = {"version": "v1", "segments": segments, "routes": routes}
        candidate = copy.deepcopy(baseline)
        candidate["version"] = "v2"
        changed = {"s3", "s19", "s48"}
        for segment in candidate["segments"]:
            if segment["id"] in changed:
                segment["geometry_revision"] = "v2"
        candidate["routes"][1]["segment_ids"].reverse()
        expected = sorted(
            row["id"]
            for index, row in enumerate(routes)
            if changed.intersection(row["segment_ids"]) or index == 1
        )
        result = audit(
            {"baseline": baseline, "candidate": candidate, "acknowledgements": []}
        )
        self.assertEqual(result["impacted_routes"], expected)
        self.assertEqual(result["missing_acknowledgements"], expected)
