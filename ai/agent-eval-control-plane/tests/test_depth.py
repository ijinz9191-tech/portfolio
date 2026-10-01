import unittest

from agent_eval_control_plane.evaluator import evaluate_run, release_gate
from agent_eval_control_plane.models import EvaluationCase, RunTrace
from test_control_plane import case_raw, run_raw


class EvaluationDepthTests(unittest.TestCase):
    def test_conflicting_casefold_fact_links_cannot_pass_by_order(self):
        case = EvaluationCase.from_dict(case_raw(grounding_required=True))
        links = [
            ("timeout", "fixture://unknown"),
            ("TIMEOUT", "fixture://trace/1"),
            ("retry", "fixture://trace/1"),
        ]
        for ordered in (links, list(reversed(links))):
            result = evaluate_run(
                case, RunTrace.from_dict(run_raw(fact_evidence=dict(ordered)))
            )
            self.assertIn("grounding_complete", result.violations)

    def test_duplicate_run_cannot_inflate_suite(self):
        result = evaluate_run(
            EvaluationCase.from_dict(case_raw()), RunTrace.from_dict(run_raw())
        )
        self.assertEqual(
            release_gate(iter([result, result]))["reason"], "duplicate_run_id"
        )

    def test_nonfinite_and_boolean_thresholds_reject(self):
        for invalid in (float("nan"), float("inf"), True, -0.1, 1.1):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                release_gate([], invalid)
