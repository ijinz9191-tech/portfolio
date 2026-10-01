import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from infra_change_evidence.validator import validate_change
from test_infra_change import change, inventory


class DependencyDepthTests(unittest.TestCase):
    def test_transitive_missing_dependency_is_in_blast_radius(self):
        assets = inventory()
        assets["assets"][1]["depends_on"] = ["storage"]
        result = validate_change(assets, change())
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("storage", result.blast_radius)

    def test_deep_chain_and_cycle_finish_without_recursion(self):
        assets = {
            "assets": [
                {
                    "id": str(i),
                    "ip": f"ip-{i}",
                    "owner": "ops",
                    "status": "active",
                    "depends_on": [str(i + 1)] if i < 1999 else ["0"],
                }
                for i in range(2000)
            ]
        }
        proposal = change()
        proposal["asset_ids"] = ["0"]
        result = validate_change(assets, proposal)
        self.assertEqual(len(result.blast_radius), 2000)
        self.assertFalse(
            next(
                row for row in result.checks if row.name == "dependency_coverage"
            ).passed
        )

    def test_duplicate_asset_id_and_invalid_dependencies_reject(self):
        assets = inventory()
        assets["assets"].append(copy.deepcopy(assets["assets"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_change(assets, change())
        assets = inventory()
        assets["assets"][0]["depends_on"] = "dns-01"
        with self.assertRaisesRegex(ValueError, "depends_on"):
            validate_change(assets, change())

    def test_boolean_is_not_a_downtime_count(self):
        proposal = change()
        proposal["expected_downtime_minutes"] = True
        self.assertFalse(
            next(
                row
                for row in validate_change(inventory(), proposal).checks
                if row.name == "downtime_budget"
            ).passed
        )
