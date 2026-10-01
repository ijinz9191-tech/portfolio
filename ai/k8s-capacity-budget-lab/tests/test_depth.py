import copy
import unittest

from capacitylab import plan
from test_planner import FIXTURE, NOW


class ExactCapacityTests(unittest.TestCase):
    def data(self):
        data = copy.deepcopy(FIXTURE)
        data.pop("monthly_cost_ceiling_usd", None)
        data["node_offerings"] = [data["node_offerings"][0]]
        data["workload"]["max_surge"] = 0
        data["workload"]["replicas"] = 2**60 + 3
        return data

    def test_integer_ceiling_survives_float_precision_boundary(self):
        data = self.data()
        result = plan(data, now=NOW)
        count, capacity = data["workload"]["replicas"], result["pods_per_node"]
        self.assertEqual(result["nodes"], (count + capacity - 1) // capacity)
        self.assertGreaterEqual(result["nodes"] * capacity, count)
        self.assertLess((result["nodes"] - 1) * capacity, count)

    def test_zone_loss_search_returns_minimal_exact_large_count(self):
        data = self.data()
        data["workload"]["survive_single_zone_loss"] = True
        result = plan(data, now=NOW)
        nodes, capacity = result["nodes"], result["pods_per_node"]
        count = data["workload"]["replicas"]
        self.assertGreaterEqual((nodes - (nodes + 1) // 2) * capacity, count)
        self.assertLess(((nodes - 1) - nodes // 2) * capacity, count)
