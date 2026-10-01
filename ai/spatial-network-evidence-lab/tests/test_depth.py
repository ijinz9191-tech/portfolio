import random
import unittest

from audit import audit


class ShortestEvidenceTests(unittest.TestCase):
    def test_dijkstra_matches_bellman_ford_on_parallel_directed_edges(self):
        generator = random.Random(901)
        names = [f"n{i}" for i in range(8)]
        nodes = [{"id": name, "lat": 37, "lon": 127} for name in names]
        edges = [
            {
                "id": f"chain-{i}",
                "from": names[i],
                "to": names[i + 1],
                "distance_m": 100,
            }
            for i in range(7)
        ]
        for i in range(30):
            source, target = generator.sample(names, 2)
            edges.append(
                {
                    "id": f"extra-{i}",
                    "from": source,
                    "to": target,
                    "distance_m": generator.randrange(1, 200),
                }
            )
        document = {
            "version": "synthetic",
            "nodes": nodes,
            "edges": edges,
            "routes": [{"id": "route", "edge_ids": [f"chain-{i}" for i in range(7)]}],
        }
        distances = {name: float("inf") for name in names}
        distances[names[0]] = 0
        for _ in range(len(names) - 1):
            for edge in edges:
                distances[edge["to"]] = min(
                    distances[edge["to"]], distances[edge["from"]] + edge["distance_m"]
                )
        route = audit(document)["routes"][0]
        self.assertEqual(route["shortest_distance_m"], distances[names[-1]])
        self.assertEqual(route["detour_distance_m"], 700 - distances[names[-1]])

    def test_cycle_to_start_has_zero_endpoint_shortest_lower_bound(self):
        document = {
            "version": "synthetic",
            "nodes": [
                {"id": "a", "lat": 37, "lon": 127},
                {"id": "b", "lat": 37, "lon": 127},
            ],
            "edges": [
                {"id": "ab", "from": "a", "to": "b", "distance_m": 10},
                {"id": "ba", "from": "b", "to": "a", "distance_m": 10},
            ],
            "routes": [
                {"id": "return", "edge_ids": ["ab", "ba"], "stops": ["a", "b", "a"]}
            ],
        }
        route = audit(document)["routes"][0]
        self.assertEqual(route["shortest_distance_m"], 0)
        self.assertEqual(route["detour_distance_m"], 20)
        self.assertIn("mandatory stops excluded", route["shortest_scope"])
