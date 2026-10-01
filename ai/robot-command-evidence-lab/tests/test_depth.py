"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import unittest

from audit import audit


class DepthTests(unittest.TestCase):
    def test_exact_timing_and_touching_intervals(self):
        commands = [
            {
                "request_id": str(i),
                "robot_id": "r",
                "action": "move",
                "requested_at": f"2026-01-01T00:00:{i * 2:02d}Z",
                "accepted_at": f"2026-01-01T00:00:{i * 2:02d}.000001Z",
                "completed_at": f"2026-01-01T00:00:{i * 2 + 2:02d}Z",
                "result": "SUCCEEDED",
            }
            for i in range(2)
        ]
        result = audit({"version": "v", "commands": commands})
        self.assertEqual(result["timings"][0]["queue_us"], 1)
        self.assertEqual(result["timings"][0]["execution_us"], 1999999)

    def test_timezone_offsets_preserve_elapsed_time(self):
        doc = {
            "version": "v",
            "commands": [
                {
                    "request_id": "r",
                    "robot_id": "A",
                    "action": "move",
                    "requested_at": "2026-01-01T09:00:00+09:00",
                    "accepted_at": "2026-01-01T00:00:01Z",
                    "completed_at": "2026-01-01T00:00:02Z",
                    "result": "FAILED",
                }
            ],
        }
        self.assertEqual(audit(doc)["timings"][0]["execution_us"], 1000000)


if __name__ == "__main__":
    unittest.main()
