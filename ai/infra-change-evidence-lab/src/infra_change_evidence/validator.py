from __future__ import annotations
import hashlib, json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

@dataclass(frozen=True)
class Decision:
    change_id: str
    status: str
    blast_radius: tuple[str, ...]
    checks: tuple[Check, ...]
    evidence_hash: str
    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["blast_radius"] = list(self.blast_radius)
        value["checks"] = [asdict(item) for item in self.checks]
        return value

def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("maintenance timestamps require a timezone")
    return parsed.astimezone(timezone.utc)

def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def validate_change(inventory: dict[str, Any], change: dict[str, Any]) -> Decision:
    change_id = str(change.get("change_id", "")).strip()
    if not change_id:
        raise ValueError("change_id is required")
    assets = inventory.get("assets")
    if not isinstance(assets, list):
        raise ValueError("inventory.assets must be a list")
    requested = change.get("asset_ids")
    if not isinstance(requested, list) or not requested:
        raise ValueError("asset_ids must be a non-empty list")

    by_id = {str(asset.get("id")): asset for asset in assets if asset.get("id")}
    checks: list[Check] = []
    missing = sorted(set(map(str, requested)) - set(by_id))
    checks.append(Check("asset_existence", not missing, "all assets found" if not missing else f"missing: {', '.join(missing)}"))

    ips = [str(a.get("ip", "")).strip() for a in assets]
    duplicate_ips = sorted({ip for ip in ips if ip and ips.count(ip) > 1})
    checks.append(Check("unique_ip_inventory", not duplicate_ips, "no duplicate IPs" if not duplicate_ips else f"duplicates: {', '.join(duplicate_ips)}"))

    selected = [by_id[item] for item in map(str, requested) if item in by_id]
    ownerless = sorted(str(a["id"]) for a in selected if not str(a.get("owner", "")).strip())
    checks.append(Check("asset_ownership", not ownerless, "owners assigned" if not ownerless else f"owner missing: {', '.join(ownerless)}"))
    inactive = sorted(str(a["id"]) for a in selected if a.get("status") != "active")
    checks.append(Check("asset_lifecycle", not inactive, "assets active" if not inactive else f"not active: {', '.join(inactive)}"))

    dependencies = sorted({str(dep) for a in selected for dep in a.get("depends_on", [])})
    uncovered = sorted(dep for dep in dependencies if dep not in set(map(str, requested)))
    checks.append(Check("dependency_coverage", not uncovered, "dependencies included" if not uncovered else f"not included: {', '.join(uncovered)}"))

    try:
        start, end = _parse_utc(str(change.get("window_start", ""))), _parse_utc(str(change.get("window_end", "")))
        duration = int((end - start).total_seconds() // 60)
        window_ok = 0 < duration <= 240
        window_detail = f"{duration} minute window" if window_ok else f"invalid {duration} minute window"
    except (ValueError, TypeError):
        window_ok, window_detail = False, "invalid maintenance window"
    checks.append(Check("maintenance_window", window_ok, window_detail))

    steps = change.get("steps")
    steps_ok = isinstance(steps, list) and len(steps) >= 2 and all(isinstance(x, str) and x.strip() for x in steps)
    checks.append(Check("execution_plan", steps_ok, "ordered plan present" if steps_ok else "at least two non-empty steps required"))
    rollback = change.get("rollback_steps")
    rollback_ok = isinstance(rollback, list) and len(rollback) >= 2 and all(isinstance(x, str) and x.strip() for x in rollback)
    checks.append(Check("rollback_plan", rollback_ok, "rollback present" if rollback_ok else "at least two rollback steps required"))

    risk = str(change.get("risk", "")).lower()
    required = {"low": 1, "medium": 2, "high": 3}.get(risk)
    approvers = {str(x).strip() for x in change.get("approvers", []) if str(x).strip()}
    approval_ok = required is not None and len(approvers) >= required
    checks.append(Check("approval_quorum", approval_ok, f"{len(approvers)} unique approvers; required {required if required else 'valid risk'}"))

    prod_assets = [a for a in selected if a.get("environment") == "production"]
    downtime = change.get("expected_downtime_minutes")
    downtime_ok = isinstance(downtime, int) and downtime >= 0 and (not prod_assets or downtime <= 30)
    checks.append(Check("downtime_budget", downtime_ok, f"{downtime} minutes" if isinstance(downtime, int) else "integer downtime required"))

    emergency = bool(change.get("emergency", False))
    ticket = str(change.get("emergency_ticket", "")).strip()
    emergency_ok = not emergency or (ticket and risk == "high" and len(approvers) >= 3)
    checks.append(Check("emergency_control", emergency_ok, "standard change" if not emergency else ("emergency evidence present" if emergency_ok else "emergency requires ticket, high risk and 3 approvers")))

    blast = sorted(set(map(str, requested)) | set(dependencies))
    source = {"inventory": inventory, "change": change, "checks": [asdict(x) for x in checks], "blast_radius": blast}
    evidence_hash = hashlib.sha256(_canonical(source)).hexdigest()
    status = "APPROVED" if all(check.passed for check in checks) else "BLOCKED"
    return Decision(change_id, status, tuple(blast), tuple(checks), evidence_hash)
