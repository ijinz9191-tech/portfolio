"""통합 검사 도구가 빈 검사·건너뜀·시간 초과를 성공으로 오인하지 않게 검증한다."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "verify_portfolio", Path(__file__).resolve().parents[1] / "verify_portfolio.py"
)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class VerificationBoundaryTests(unittest.TestCase):
    def run_fixture(self, test_source):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "ai" / "fixture"
            (directory / "tests").mkdir(parents=True)
            (directory / "tests" / "test_example.py").write_text(
                test_source, encoding="utf-8"
            )
            return VERIFY.run_project(
                {"id": "fixture", "title": "가상 검사", "runtime": "python"},
                root,
                SimpleNamespace(timeout=10),
            )

    def test_empty_suite_cannot_pass(self):
        result = self.run_fixture("import unittest\n")
        self.assertEqual(result["tests"], 0)
        self.assertEqual(result["status"], "FAIL")

    def test_skipped_suite_cannot_pass(self):
        result = self.run_fixture(
            "import unittest\nclass Case(unittest.TestCase):\n"
            "    @unittest.skip('가상 미검증')\n"
            "    def test_skipped(self): pass\n"
        )
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["status"], "FAIL")

    def test_assertion_failure_is_preserved(self):
        result = self.run_fixture(
            "import unittest\nclass Case(unittest.TestCase):\n"
            "    def test_failure(self): self.assertEqual(1, 2)\n"
        )
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["stages"][0]["exit_code"], 1)
        self.assertEqual(result["status"], "FAIL")

    def test_success_has_current_source_fingerprint(self):
        result = self.run_fixture(
            "import unittest\nclass Case(unittest.TestCase):\n"
            "    def test_success(self): self.assertEqual(2 + 2, 4)\n"
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["tests"], 1)
        self.assertEqual(len(result["source_hash"]), 64)
        self.assertTrue(result["source_unchanged_during_run"])

    def test_java_title_number_is_not_a_summary(self):
        count, failures = VERIFY.parse_java_summary(
            "PASS 32개 실제 병행 요청\nRESULT 14 passed, 0 failed\n"
        )
        self.assertEqual((count, failures), (14, 0))

    def test_java_missing_or_trailing_summary_cannot_pass(self):
        for output in ("PASS 32개 요청", "RESULT 14 passed, 0 failed\nunexpected"):
            self.assertEqual(VERIFY.parse_java_summary(output), (0, 0))

    def test_java_failed_summary_is_preserved(self):
        self.assertEqual(
            VERIFY.parse_java_summary("RESULT 13 passed, 1 failed"), (14, 1)
        )

    def test_java_delivery_ratio_uses_total_and_failure_count(self):
        self.assertEqual(VERIFY.parse_java_summary("PASS 22/22"), (22, 0))
        self.assertEqual(VERIFY.parse_java_summary("PASS 21/22"), (22, 1))
        self.assertEqual(VERIFY.parse_java_summary("PASS 23/22"), (0, 0))
        self.assertEqual(
            VERIFY.parse_java_summary("PASS 2/2\n  PASS create\n  PASS 20개 요청"),
            (2, 0),
        )
        self.assertEqual(VERIFY.parse_java_summary("PASS 2/2\n  PASS create"), (0, 0))

    def test_nested_python_process_inherits_utf8(self):
        script = """
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-c", "print('한글 검증')"],
    capture_output=True, encoding="utf-8", check=True
)
print(result.stdout, end="")
"""
        with mock.patch.dict(
            os.environ, {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp949"}
        ):
            code, output = VERIFY.execute(
                [sys.executable, "-c", script], Path(__file__).parent, timeout=30
            )
        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), "한글 검증")

    def test_timeout_returns_explicit_failure(self):
        code, output = VERIFY.execute(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            Path(__file__).parent,
            timeout=1,
        )
        self.assertEqual(code, 124)
        self.assertIn("시간 초과", output)


if __name__ == "__main__":
    unittest.main()
