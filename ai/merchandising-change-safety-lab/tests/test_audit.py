import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from audit import ChangeError, analyze


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / "samples" / "safe-change.json").read_text(encoding="utf-8"))


class ChangeTests(unittest.TestCase):
    def test_safe_change(self):
        result = analyze(fixture())
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["impacts"][0]["after_effective_price"], 9000)

    def test_stale_version_blocks(self):
        data = fixture()
        data["proposed"][0]["version"] = 2
        self.assertEqual(analyze(data)["decision"], "BLOCK")

    def test_price_below_cost_blocks(self):
        data = fixture()
        data["proposed"][0]["discount"] = 5000
        self.assertEqual(analyze(data)["decision"], "BLOCK")

    def test_large_price_drop_requires_review(self):
        data = fixture()
        data["proposed"][0]["price"] = 7000
        data["proposed"][0]["discount"] = 0
        self.assertEqual(analyze(data)["decision"], "REVIEW")

    def test_stocked_product_removal_blocks(self):
        data = fixture()
        data["proposed"] = []
        data["removed"] = [{"sku": "ITEM-01", "expected_version": 3}]
        self.assertEqual(analyze(data)["decision"], "BLOCK")
        data["current"][0]["stock"] = 0
        self.assertEqual(analyze(data)["decision"], "PASS")

    def test_duplicate_or_boolean_number_rejected(self):
        data = fixture()
        data["proposed"].append(copy.deepcopy(data["proposed"][0]))
        with self.assertRaises(ChangeError):
            analyze(data)
        data = fixture()
        data["proposed"][0]["price"] = True
        with self.assertRaises(ChangeError):
            analyze(data)

    def test_order_independent_digest(self):
        data = fixture()
        data["current"].append({"sku": "ITEM-02", "version": 1, "cost": 100,
                                "price": 200, "discount": 0, "stock": 0})
        reversed_data = copy.deepcopy(data)
        reversed_data["current"].reverse()
        self.assertEqual(analyze(data)["evidence_sha256"], analyze(reversed_data)["evidence_sha256"])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "change.json"
            data = fixture()
            path.write_text(json.dumps(data), encoding="utf-8")
            ok = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(path)],
                                capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            data["proposed"][0]["version"] = 2
            path.write_text(json.dumps(data), encoding="utf-8")
            bad = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(path)],
                                 capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)


if __name__ == "__main__":
    unittest.main()
