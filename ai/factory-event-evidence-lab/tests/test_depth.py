"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import unittest

from audit import AuditError, audit


class DepthTests(unittest.TestCase):
    def test_durations_and_input_permutation(self):
        doc = {
            "version": "v",
            "route": ["a", "b"],
            "events": [
                {
                    "id": str(i),
                    "lot": "L",
                    "station": station,
                    "kind": kind,
                    "at": f"2026-01-01T00:00:0{i}+00:00",
                }
                for i, (station, kind) in enumerate(
                    [
                        ("a", "START"),
                        ("a", "COMPLETE"),
                        ("b", "START"),
                        ("b", "COMPLETE"),
                    ]
                )
            ],
        }
        result = audit(doc)
        self.assertEqual(
            [row["duration_us"] for row in result["station_intervals"]],
            [1000000, 1000000],
        )
        doc["events"].reverse()
        self.assertEqual(audit(doc), result)

    def test_half_open_station_concurrency(self):
        doc = {
            "version": "v",
            "route": ["a"],
            "events": [
                {
                    "id": f"{lot}-{kind}",
                    "lot": lot,
                    "station": "a",
                    "kind": kind,
                    "at": f"2026-01-01T00:00:0{time}Z",
                }
                for lot, start, end in (("L1", 0, 2), ("L2", 1, 3), ("L3", 3, 4))
                for kind, time in (("START", start), ("COMPLETE", end))
            ],
        }
        self.assertEqual(
            audit(doc)["station_load"], [{"station": "a", "peak_simultaneous_lots": 2}]
        )

    def test_bad_station_type_is_domain_error(self):
        doc = {
            "version": "v",
            "route": ["a"],
            "events": [
                {
                    "id": "e",
                    "lot": "L",
                    "station": [],
                    "kind": "START",
                    "at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        with self.assertRaises(AuditError):
            audit(doc)


if __name__ == "__main__":
    unittest.main()
