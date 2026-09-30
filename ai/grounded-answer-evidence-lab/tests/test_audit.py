"""가상 답변의 근거 추적 검사를 검증한다."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit import audit  # noqa: E402


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((ROOT / "samples" / "answer.json").read_text(encoding="utf-8"))

    def test_sample_is_traceable(self):
        result = audit(self.payload)
        self.assertTrue(result["traceable"])
        self.assertEqual(result["claim_count"], 2)

    def test_unknown_document_fails(self):
        value = copy.deepcopy(self.payload)
        value["claims"][0]["citations"][0]["source_id"] = "없는-문서"
        self.assertIn("존재하지 않는 문서", audit(value)["results"][0]["problems"])

    def test_stale_document_hash_fails(self):
        value = copy.deepcopy(self.payload)
        value["documents"][0]["text"] += " 변경됨"
        self.assertIn("문서 버전 불일치", audit(value)["results"][0]["problems"])

    def test_fabricated_quote_fails(self):
        value = copy.deepcopy(self.payload)
        value["claims"][0]["citations"][0]["quote"] = "문서에는 없는 허구의 운영 사실"
        self.assertIn("문서에 없는 인용", audit(value)["results"][0]["problems"])

    def test_missing_citation_fails_closed(self):
        value = copy.deepcopy(self.payload)
        value["claims"][0]["citations"] = []
        with self.assertRaises(ValueError):
            audit(value)

    def test_duplicate_document_id_is_rejected(self):
        value = copy.deepcopy(self.payload)
        value["documents"].append(value["documents"][0])
        with self.assertRaises(ValueError):
            audit(value)

    def test_cli_returns_failure_for_untraceable_claim(self):
        import tempfile

        value = copy.deepcopy(self.payload)
        value["claims"][0]["citations"][0]["quote"] = "허구의 사실은 문서에 없다"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "audit.py"), str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["traceable"])


if __name__ == "__main__":
    unittest.main()
