"""가상 이동 경로의 연결·거리·지정 경유지를 오프라인에서 검증한다."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import sys
from pathlib import Path


class SpatialError(ValueError):
    """경로 근거가 부족하거나 내부에서 서로 맞지 않는다."""


def _identifier(value: object, kind: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise SpatialError(f"{kind} id must be a bounded nonempty string")
    return value


def _coordinate(value: object, low: float, high: float, name: str) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise SpatialError(f"{name} is out of range")
    return float(value)


def _meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 12_742_000 * math.asin(min(1.0, math.sqrt(h)))


def audit(document: dict) -> dict:
    if not isinstance(document, dict) or set(document) != {
        "version",
        "nodes",
        "edges",
        "routes",
    }:
        raise SpatialError("version, nodes, edges and routes are required")
    version = _identifier(document["version"], "version")
    nodes_raw, edges_raw, routes_raw = (
        document[name] for name in ("nodes", "edges", "routes")
    )
    if not all(
        isinstance(rows, list) and 1 <= len(rows) <= 1000
        for rows in (nodes_raw, edges_raw, routes_raw)
    ):
        raise SpatialError("each collection requires 1 to 1000 rows")
    nodes: dict[str, tuple[float, float]] = {}
    for row in nodes_raw:
        if not isinstance(row, dict) or set(row) != {"id", "lat", "lon"}:
            raise SpatialError("node fields are incomplete")
        key = _identifier(row["id"], "node")
        if key in nodes:
            raise SpatialError("duplicate node id")
        nodes[key] = (
            _coordinate(row["lat"], -90, 90, "latitude"),
            _coordinate(row["lon"], -180, 180, "longitude"),
        )
    edges: dict[str, tuple[str, str, float]] = {}
    for row in edges_raw:
        if not isinstance(row, dict) or set(row) != {"id", "from", "to", "distance_m"}:
            raise SpatialError("edge fields are incomplete")
        key = _identifier(row["id"], "edge")
        source, target = (
            _identifier(row["from"], "source"),
            _identifier(row["to"], "target"),
        )
        if (
            key in edges
            or source == target
            or source not in nodes
            or target not in nodes
        ):
            raise SpatialError("duplicate, self-loop or dangling edge")
        claimed = row["distance_m"]
        if (
            type(claimed) not in (int, float)
            or not math.isfinite(claimed)
            or claimed <= 0
        ):
            raise SpatialError("edge distance must be positive and finite")
        direct = _meters(nodes[source], nodes[target])
        if claimed + 1 < direct:
            raise SpatialError("edge distance is shorter than geodesic distance")
        edges[key] = (source, target, float(claimed))
    adjacency = {key: [] for key in nodes}
    for source, target, distance in edges.values():
        adjacency[source].append((target, distance))
    shortest_cache = {}

    def shortest_from(source):
        # 동일 출발지의 경로들은 양의 가중치 최단거리 인덱스를 공유한다.
        if source not in shortest_cache:
            distances = {source: 0.0}
            pending = [(0.0, source)]
            while pending:
                distance, node = heapq.heappop(pending)
                if distance != distances[node]:
                    continue
                for target, weight in adjacency[node]:
                    candidate = distance + weight
                    if candidate < distances.get(target, math.inf):
                        distances[target] = candidate
                        heapq.heappush(pending, (candidate, target))
            shortest_cache[source] = distances
        return shortest_cache[source]

    results = []
    route_ids = set()
    for row in routes_raw:
        if (
            not isinstance(row, dict)
            or not {"id", "edge_ids"} <= set(row)
            or set(row) - {"id", "edge_ids", "stops"}
        ):
            raise SpatialError("route fields are incomplete")
        key = _identifier(row["id"], "route")
        path = row["edge_ids"]
        if key in route_ids or not isinstance(path, list) or not 1 <= len(path) <= 1000:
            raise SpatialError("route id or edge sequence invalid")
        route_ids.add(key)
        if any(not isinstance(edge, str) or edge not in edges for edge in path):
            raise SpatialError("route references unknown edge")
        for left, right in zip(path, path[1:]):
            if edges[left][1] != edges[right][0]:
                raise SpatialError("route has a disconnected handoff")
        visited = [edges[path[0]][0], *(edges[edge][1] for edge in path)]
        if "stops" in row:
            stops = row["stops"]
            if (
                not isinstance(stops, list)
                or len(stops) < 2
                or len(stops) > len(visited)
                or any(not isinstance(stop, str) or stop not in nodes for stop in stops)
            ):
                raise SpatialError("route stops are invalid")
            if stops[0] != visited[0] or stops[-1] != visited[-1]:
                raise SpatialError("route endpoints do not match planned stops")
            cursor = 0
            for stop in stops:
                while cursor < len(visited) and visited[cursor] != stop:
                    cursor += 1
                if cursor == len(visited):
                    raise SpatialError("route misses or reorders a planned stop")
                cursor += 1
        start, end = edges[path[0]][0], edges[path[-1]][1]
        route_distance = math.fsum(edges[edge][2] for edge in path)
        shortest = shortest_from(start)[end]
        results.append(
            {
                "id": key,
                "start": start,
                "end": end,
                "distance_m": round(route_distance, 2),
                "shortest_distance_m": round(shortest, 2),
                "detour_distance_m": round(max(0.0, route_distance - shortest), 2),
                "shortest_scope": "directed endpoint path; mandatory stops excluded",
                "edge_count": len(path),
            }
        )
    canonical = {
        "version": version,
        "nodes": sorted(nodes_raw, key=lambda row: row["id"]),
        "edges": sorted(edges_raw, key=lambda row: row["id"]),
        "routes": sorted(routes_raw, key=lambda row: row["id"]),
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "decision": "TOPOLOGY_VERIFIED",
        "version": version,
        "nodes": len(nodes),
        "edges": len(edges),
        "routes": sorted(results, key=lambda row: row["id"]),
        "evidence_sha256": digest,
        "limits": "Synthetic topology and straight-line lower-bound evidence only; no map accuracy or production routing claim.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python audit.py NETWORK.json", file=sys.stderr)
        return 2
    try:
        result = audit(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, SpatialError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
