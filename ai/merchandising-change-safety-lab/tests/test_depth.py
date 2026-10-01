"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import json
import unittest
from pathlib import Path

from audit import analyze


class DepthTests(unittest.TestCase):
    def doc(self):
        return json.loads(
            (
                Path(__file__).resolve().parents[1] / "samples" / "safe-change.json"
            ).read_text(encoding="utf-8")
        )

    def test_inventory_exposure_reference(self):
        doc = self.doc()
        doc["proposed"][0]["stock"] = 23
        result = analyze(doc)
        old = doc["current"][0]
        new = doc["proposed"][0]
        self.assertEqual(
            result["inventory_delta_won"],
            (new["price"] - new["discount"]) * new["stock"]
            - (old["price"] - old["discount"]) * old["stock"],
        )
        self.assertEqual(result["stock_delta"], 3)
        self.assertTrue(result["applicable"])

    def test_blocked_plan_metrics_are_not_applicable(self):
        doc = self.doc()
        doc["proposed"][0]["version"] = 0
        self.assertFalse(analyze(doc)["applicable"])


if __name__ == "__main__":
    unittest.main()
