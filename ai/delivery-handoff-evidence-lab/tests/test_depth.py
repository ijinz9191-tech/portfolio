"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import json
import unittest
from pathlib import Path

from audit import audit


class DepthTests(unittest.TestCase):
    def doc(self):
        return json.loads(
            (Path(__file__).resolve().parents[1] / "samples" / "routes.json").read_text(
                encoding="utf-8"
            )
        )

    def test_slack_and_transition_duration_reference(self):
        doc = self.doc()
        result = audit(doc)
        self.assertEqual(len(result["diagnostics"]), len(doc["deliveries"]))
        for item, actual in zip(
            sorted(doc["deliveries"], key=lambda row: row["id"]), result["diagnostics"]
        ):
            complete = next(
                (e["at_min"] for e in item["events"] if e["stage"] == "completed"),
                doc["now_min"],
            )
            self.assertEqual(actual["slack_min"], item["deadline_min"] - complete)
            self.assertEqual(
                sum(t["elapsed_min"] for t in actual["observed_transitions"]),
                item["events"][-1]["at_min"] - item["events"][0]["at_min"],
            )

    def test_gap_keeps_actual_observations_only(self):
        doc = self.doc()
        doc["deliveries"][0]["events"].pop(2)
        result = audit(doc)
        self.assertEqual(result["deliveries"][0]["decision"], "EVIDENCE_GAP")
        self.assertEqual(len(result["diagnostics"][0]["observed_transitions"]), 2)


if __name__ == "__main__":
    unittest.main()
