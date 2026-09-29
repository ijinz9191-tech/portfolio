import copy
import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from capacitylab import PlanError, plan


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "samples" / "rollout.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 9, 29, 0, 1, tzinfo=timezone.utc)


class PlannerTests(unittest.TestCase):
    def sample(self):
        return copy.deepcopy(FIXTURE)

    def test_cheapest_feasible_plan_accounts_for_rollout_surge(self):
        result = plan(self.sample(), now=NOW)
        self.assertEqual(result["node_offering"], "small")
        self.assertEqual(result["rollout_pods"], 8)
        self.assertEqual(result["nodes"], 4)
        self.assertEqual(result["zone_nodes"], {"a": 2, "b": 2})
        self.assertEqual(result["monthly_cost_usd"], "233.60")

    def test_memory_is_a_real_packing_limit(self):
        data = self.sample()
        data["telemetry"]["p95_memory_mib_per_pod"] = 2100
        data["monthly_cost_ceiling_usd"] = 600
        result = plan(data, now=NOW)
        self.assertEqual(result["pods_per_node"], 1)
        self.assertEqual(result["nodes"], 8)

    def test_minimum_two_zones_even_if_one_node_has_capacity(self):
        data = self.sample()
        data["workload"]["replicas"] = 1
        data["workload"]["max_surge"] = 0
        self.assertEqual(plan(data, now=NOW)["nodes"], 2)

    def test_single_zone_loss_preserves_steady_state_replicas(self):
        data = self.sample()
        data["workload"]["survive_single_zone_loss"] = True
        data["monthly_cost_ceiling_usd"] = 1000
        result = plan(data, now=NOW)
        self.assertEqual(result["nodes"], 6)
        self.assertEqual(result["zone_nodes"], {"a": 3, "b": 3})
        self.assertGreaterEqual(result["surviving_pods_after_zone_loss"], data["workload"]["replicas"])
        self.assertEqual(result["single_zone_loss_required"], True)

    def test_zone_loss_can_make_cost_ceiling_infeasible(self):
        data = self.sample()
        data["workload"]["survive_single_zone_loss"] = True
        with self.assertRaisesRegex(PlanError, "cost ceiling"):
            plan(data, now=NOW)

    def test_zone_loss_flag_rejects_non_boolean(self):
        data = self.sample()
        data["workload"]["survive_single_zone_loss"] = "yes"
        with self.assertRaisesRegex(PlanError, "boolean"):
            plan(data, now=NOW)

    def test_large_zone_loss_plan_uses_bounded_search(self):
        data = self.sample()
        data["workload"]["replicas"] = 1_000_000
        data["workload"]["survive_single_zone_loss"] = True
        data["monthly_cost_ceiling_usd"] = 100_000_000
        result = plan(data, now=NOW)
        self.assertGreaterEqual(result["surviving_pods_after_zone_loss"], 1_000_000)
        self.assertLess(result["nodes"], 1_000_001)

    def test_large_rollout_distributes_nodes_without_per_node_iteration(self):
        data = self.sample()
        data["workload"]["replicas"] = 1_000_000
        data["monthly_cost_ceiling_usd"] = 100_000_000
        result = plan(data, now=NOW)
        self.assertEqual(sum(result["zone_nodes"].values()), result["nodes"])
        self.assertLessEqual(max(result["zone_nodes"].values()) - min(result["zone_nodes"].values()), 1)

    def test_rejects_stale_and_future_telemetry(self):
        data = self.sample()
        data["telemetry"]["observed_at"] = "2026-09-28T23:00:00Z"
        with self.assertRaisesRegex(PlanError, "stale"):
            plan(data, now=NOW)
        data["telemetry"]["observed_at"] = "2026-09-29T00:02:00Z"
        with self.assertRaisesRegex(PlanError, "future"):
            plan(data, now=NOW)

    def test_rejects_cost_ceiling(self):
        data = self.sample()
        data["monthly_cost_ceiling_usd"] = 100
        with self.assertRaisesRegex(PlanError, "cost ceiling"):
            plan(data, now=NOW)

    def test_rejects_missing_zone_diversity_and_unfit_nodes(self):
        data = self.sample()
        for offer in data["node_offerings"]:
            offer["zones"] = ["a"]
        with self.assertRaisesRegex(PlanError, "no node offering"):
            plan(data, now=NOW)
        data = self.sample()
        for offer in data["node_offerings"]:
            offer["memory_mib"] = 128
        with self.assertRaisesRegex(PlanError, "no node offering"):
            plan(data, now=NOW)

    def test_rejects_ambiguous_or_invalid_inputs(self):
        data = self.sample()
        data["node_offerings"][1]["id"] = "small"
        with self.assertRaisesRegex(PlanError, "unique"):
            plan(data, now=NOW)
        data = self.sample()
        data["workload"]["replicas"] = True
        with self.assertRaisesRegex(PlanError, "replicas"):
            plan(data, now=NOW)
        data = self.sample()
        data["workload"]["target_cpu_utilization"] = 0
        with self.assertRaisesRegex(PlanError, "target_cpu"):
            plan(data, now=NOW)

    def test_cli_normal_and_rejection_exit_codes(self):
        command = [sys.executable, "-m", "capacitylab", str(ROOT / "samples" / "rollout.json"), "--now", "2026-09-29T00:01:00Z"]
        ok = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["rollout_pods"], 8)
        rejected = subprocess.run(command[:-2] + ["--now", "2026-09-29T00:10:00Z"], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("REJECTED", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
