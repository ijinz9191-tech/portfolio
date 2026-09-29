"""Deterministic diagnosis of synthetic service path probes; no network access."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PHASES = ("dns", "service", "endpoint", "policy", "mesh", "application")
NEXT_PROBE = {
    "dns": "Compare pod resolver answer with the intended service name and TTL.",
    "service": "Check Service selector, port and ClusterIP against the workload.",
    "endpoint": "Check EndpointSlice readiness and zone distribution.",
    "policy": "Check source and destination NetworkPolicy decisions.",
    "mesh": "Check sidecar presence, mTLS mode and proxy route configuration.",
    "application": "Check application health and upstream timeout budget.",
}


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include an offset")
    return parsed.astimezone(timezone.utc)


def diagnose(scenario: dict, now: str, max_age_seconds: int = 300) -> dict:
    """Return a first-fault hypothesis only when every observation is fresh."""
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    observed_at = _instant(now)
    probes = scenario.get("probes")
    if not isinstance(probes, list) or len(probes) != len(PHASES):
        raise ValueError("exactly one probe per phase is required")
    by_phase = {}
    evidence_by_phase = {}
    for probe in probes:
        if not isinstance(probe, dict) or probe.get("phase") not in PHASES:
            raise ValueError("invalid probe phase")
        phase = probe["phase"]
        if phase in by_phase or probe.get("result") not in ("PASS", "FAIL", "UNKNOWN"):
            raise ValueError("duplicate phase or invalid result")
        age = (observed_at - _instant(str(probe.get("observed_at", "")))).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise ValueError(f"stale or future probe: {phase}")
        by_phase[phase] = probe["result"]
        evidence_by_phase[phase] = {"phase": phase, "result": probe["result"], "observed_at": probe["observed_at"]}
    if set(by_phase) != set(PHASES):
        raise ValueError("missing phase")

    first_nonpass = next((phase for phase in PHASES if by_phase[phase] != "PASS"), None)
    if first_nonpass is None:
        status, hypothesis, next_probe = "HEALTHY", None, None
    elif by_phase[first_nonpass] == "UNKNOWN":
        status, hypothesis, next_probe = "INSUFFICIENT_EVIDENCE", None, NEXT_PROBE[first_nonpass]
    else:
        status, hypothesis, next_probe = "FAULT_CANDIDATE", first_nonpass, NEXT_PROBE[first_nonpass]

    canonical = json.dumps({"probes": [evidence_by_phase[p] for p in PHASES], "now": now, "max_age_seconds": max_age_seconds}, sort_keys=True, separators=(",", ":"))
    return {
        "status": status,
        "first_fault_candidate": hypothesis,
        "next_probe": next_probe,
        "downstream_failures": [p for p in PHASES[PHASES.index(first_nonpass) + 1:] if by_phase[p] == "FAIL"] if first_nonpass else [],
        "evidence_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "scope": "synthetic diagnostic hypothesis; operator verification required",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--now", required=True, help="explicit ISO 8601 timestamp with offset")
    parser.add_argument("--max-age-seconds", type=int, default=300)
    args = parser.parse_args()
    result = diagnose(json.loads(args.scenario.read_text(encoding="utf-8")), args.now, args.max_age_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
