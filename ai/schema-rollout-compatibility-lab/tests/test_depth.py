"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import copy
import json
import unittest
from pathlib import Path

from audit import InputError, audit


class DepthTests(unittest.TestCase):
    def doc(self):
        return json.loads(
            (
                Path(__file__).resolve().parents[1] / "samples" / "expand-migrate.json"
            ).read_text(encoding="utf-8")
        )

    def test_cache_reuses_same_pair_without_losing_stage_findings(self):
        doc = self.doc()
        stage = copy.deepcopy(doc["stages"][0])
        stage["running_apps"] = ["new"]
        stage["rollback_app"] = "new"
        doc["stages"] = [dict(stage, name=str(i)) for i in range(1000)]
        result = audit(doc)
        self.assertEqual(result["contracts_checked"], 1)
        self.assertEqual(result["stages_checked"], 1000)
        self.assertEqual(len(result["findings"]), 2000)
        self.assertEqual(
            {f["stage"] for f in result["findings"]}, {str(i) for i in range(1000)}
        )

    def test_unhashable_reference_becomes_contract_error(self):
        for field in ("schema", "rollback_app"):
            doc = self.doc()
            doc["stages"][0][field] = []
            with self.assertRaises(InputError):
                audit(doc)


if __name__ == "__main__":
    unittest.main()
