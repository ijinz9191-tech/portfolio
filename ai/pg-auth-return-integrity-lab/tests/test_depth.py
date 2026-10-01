"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import copy
import json
import unittest
from pathlib import Path

from audit import InputError, audit


class DepthTests(unittest.TestCase):
    def test_nonce_cannot_be_reused(self):
        doc = json.loads(
            next(
                (Path(__file__).resolve().parents[1] / "samples").glob("*.json")
            ).read_text(encoding="utf-8")
        )
        row = copy.deepcopy(doc["sessions"][0])
        row["session_id"] = "s-new"
        row["order_id"] = "o-new"
        doc["sessions"].append(row)
        with self.assertRaisesRegex(InputError, "nonce"):
            audit(doc)

    def test_digest_is_permutation_invariant(self):
        doc = json.loads(
            next(
                (Path(__file__).resolve().parents[1] / "samples").glob("*.json")
            ).read_text(encoding="utf-8")
        )
        # 서로 다른 nonce를 갖는 정상 세션 집합을 구성한다.
        second = copy.deepcopy(doc["sessions"][0])
        second["session_id"] = "s-2"
        second["order_id"] = "o-2"
        second["nonce_sha256"] = "0" * 64
        doc["sessions"].append(second)
        expected = audit(doc)["evidence_sha256"]
        doc["sessions"].reverse()
        self.assertEqual(audit(doc)["evidence_sha256"], expected)


if __name__ == "__main__":
    unittest.main()
