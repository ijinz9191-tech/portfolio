"""Fail-closed capacity estimate for one workload, one node shape, and N zones.

This is an offline decision aid. It does not schedule pods or inspect clusters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import ceil


class PlanError(ValueError):
    """Input or safety gate rejected the plan."""


def _integer(value, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PlanError(f"{name} must be an integer >= {minimum}")
    return value


def _decimal(value, name: str, minimum: str = "0", maximum: str | None = None) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PlanError(f"{name} must be numeric") from exc
    if isinstance(value, bool) or not result.is_finite() or result < Decimal(minimum) or (maximum is not None and result > Decimal(maximum)):
        raise PlanError(f"{name} is out of range")
    return result


def _timestamp(value, name: str) -> datetime:
    if not isinstance(value, str):
        raise PlanError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlanError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise PlanError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def plan(data: dict, *, now: datetime | None = None) -> dict:
    """Return the cheapest feasible uniform node shape with rollout surge.

    Every configured zone receives at least one node; extra nodes are placed in
    the cheapest shape's zones in order. The model assumes independent zone
    placement and per-node capacity after a fixed system reserve.
    """
    if not isinstance(data, dict):
        raise PlanError("input must be a JSON object")
    workload = data.get("workload")
    telemetry = data.get("telemetry")
    offerings = data.get("node_offerings")
    if not isinstance(workload, dict) or not isinstance(telemetry, dict) or not isinstance(offerings, list) or not offerings:
        raise PlanError("workload, telemetry and nonempty node_offerings are required")
    replicas = _integer(workload.get("replicas"), "replicas", 1)
    surge = _integer(workload.get("max_surge"), "max_surge")
    cpu_request = _integer(workload.get("cpu_request_m"), "cpu_request_m", 1)
    memory_request = _integer(workload.get("memory_request_mib"), "memory_request_mib", 1)
    min_zones = _integer(workload.get("min_zones"), "min_zones", 2)
    target_cpu = _decimal(workload.get("target_cpu_utilization"), "target_cpu_utilization", "0.01", "1")
    memory_headroom = _decimal(workload.get("memory_headroom_fraction"), "memory_headroom_fraction", "0", "1")
    reserve = _decimal(data.get("system_reserve_fraction", "0.1"), "system_reserve_fraction", "0", "0.5")
    max_age = _integer(data.get("max_telemetry_age_seconds", 300), "max_telemetry_age_seconds", 1)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise PlanError("now must include a timezone")
    age = (now.astimezone(timezone.utc) - _timestamp(telemetry.get("observed_at"), "observed_at")).total_seconds()
    if age < 0 or age > max_age:
        raise PlanError("telemetry is stale or future-dated")
    observed_cpu = _integer(telemetry.get("p95_cpu_m_per_pod"), "p95_cpu_m_per_pod")
    observed_memory = _integer(telemetry.get("p95_memory_mib_per_pod"), "p95_memory_mib_per_pod")
    effective_cpu = max(cpu_request, ceil(Decimal(observed_cpu) / target_cpu))
    effective_memory = max(memory_request, ceil(Decimal(observed_memory) * (1 + memory_headroom)))
    required_pods = replicas + surge
    cost_ceiling = data.get("monthly_cost_ceiling_usd")
    if cost_ceiling is not None:
        cost_ceiling = _decimal(cost_ceiling, "monthly_cost_ceiling_usd")
    candidates = []
    seen_ids = set()
    for index, offer in enumerate(offerings):
        if not isinstance(offer, dict) or not isinstance(offer.get("id"), str) or not offer["id"].strip():
            raise PlanError(f"node_offerings[{index}].id is required")
        offer_id = offer["id"]
        if offer_id in seen_ids:
            raise PlanError("node offering ids must be unique")
        seen_ids.add(offer_id)
        cpu = _integer(offer.get("cpu_m"), f"{offer_id}.cpu_m", 1)
        memory = _integer(offer.get("memory_mib"), f"{offer_id}.memory_mib", 1)
        max_pods = _integer(offer.get("max_pods"), f"{offer_id}.max_pods", 1)
        hourly = _decimal(offer.get("hourly_cost_usd"), f"{offer_id}.hourly_cost_usd", "0.000001")
        zones = offer.get("zones")
        if not isinstance(zones, list) or any(not isinstance(z, str) or not z.strip() for z in zones) or len(zones) != len(set(zones)):
            raise PlanError(f"{offer_id}.zones must be unique nonempty names")
        if len(zones) < min_zones:
            continue
        pods_per_node = min(max_pods, int(Decimal(cpu) * (1 - reserve)) // effective_cpu,
                            int(Decimal(memory) * (1 - reserve)) // effective_memory)
        if pods_per_node < 1:
            continue
        nodes = max(min_zones, ceil(required_pods / pods_per_node))
        monthly = hourly * nodes * 730
        extra_each, extra_remainder = divmod(nodes - min_zones, min_zones)
        zone_nodes = {
            zone: 1 + extra_each + (index < extra_remainder)
            for index, zone in enumerate(zones[:min_zones])
        }
        candidates.append((monthly, nodes, offer_id, {
            "node_offering": offer_id,
            "nodes": nodes,
            "zone_nodes": zone_nodes,
            "pods_per_node": pods_per_node,
            "rollout_pods": required_pods,
            "effective_cpu_m_per_pod": effective_cpu,
            "effective_memory_mib_per_pod": effective_memory,
            "monthly_cost_usd": str(monthly.quantize(Decimal("0.01"))),
            "assumptions": ["uniform node shape", "730-hour month", "one node per required zone", "requests and p95 telemetry only"]
        }))
    if not candidates:
        raise PlanError("no node offering can fit the workload and zone policy")
    best = min(candidates, key=lambda item: item[:3])
    if cost_ceiling is not None and best[0] > cost_ceiling:
        raise PlanError("minimum feasible plan exceeds monthly cost ceiling")
    return best[3]
