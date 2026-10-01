"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import json
import unittest
from pathlib import Path

from audit import ContractError, analyze


class DepthTests(unittest.TestCase):
    def doc(self):
        return json.loads(
            (Path(__file__).resolve().parents[1] / "samples" / "change.json").read_text(
                encoding="utf-8"
            )
        )

    def test_ambiguous_template_collision(self):
        doc = self.doc()
        doc["after"] = [
            {"route": route, "auth": "authenticated", "fields": ["id"]}
            for route in ("GET /orders/{id}", "GET /orders/{name}")
        ]
        with self.assertRaises(ContractError):
            analyze(doc)

    def test_path_traversal_and_encoding_rejected(self):
        for route in (
            "GET /orders/../admin",
            "GET /orders%2fadmin",
            "GET /orders?x=1",
            "GET /orders/{bad-name}",
        ):
            doc = self.doc()
            doc["after"][0]["route"] = route
            with self.subTest(route=route), self.assertRaises(ContractError):
                analyze(doc)

    def test_distinct_http_methods_allowed(self):
        doc = self.doc()
        doc["after"].append(
            {"route": "POST /orders", "auth": "authenticated", "fields": ["id"]}
        )
        self.assertEqual(analyze(doc)["decision"], "PASS")


if __name__ == "__main__":
    unittest.main()
