"""Fail-closed multiwindow error-budget burn decision."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation


class BurnError(ValueError):
    """The evidence is invalid, incomplete, or stale."""


def _utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise BurnError("bucket end must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BurnError("bucket end must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise BurnError("bucket end must include timezone")
    return parsed.astimezone(timezone.utc)


def assess(data: dict, *, now: datetime | None = None) -> dict:
    """Compare 5m/1h and 30m/6h burns against fixed alert thresholds.

    All windows are request weighted. Unknown or missing buckets never become
    zero-error evidence. This tool evaluates one service at one point in time.
    """
    if not isinstance(data, dict) or set(data) != {"service", "objective", "buckets"}:
        raise BurnError("service, objective and buckets are required")
    service = data["service"]
    if not isinstance(service, str) or not service.strip() or len(service) > 80:
        raise BurnError("service must be a nonempty name")
    try:
        objective = Decimal(str(data["objective"]))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BurnError("objective must be numeric") from exc
    if isinstance(data["objective"], bool) or not objective.is_finite() or not Decimal("0") < objective < Decimal("1"):
        raise BurnError("objective must be between zero and one")
    buckets = data["buckets"]
    if not isinstance(buckets, list) or len(buckets) < 72 or len(buckets) > 288:
        raise BurnError("72 to 288 five-minute buckets are required")
    cleaned = []
    previous = None
    for index, bucket in enumerate(buckets):
        if not isinstance(bucket, dict) or set(bucket) != {"end", "total", "failed"}:
            raise BurnError(f"bucket {index} has missing or unexpected fields")
        end = _utc(bucket["end"])
        if end.second or end.microsecond or end.minute % 5:
            raise BurnError("bucket ends must align to five-minute UTC boundaries")
        if previous is not None and end - previous != timedelta(minutes=5):
            raise BurnError("bucket sequence has a gap, overlap or reversal")
        previous = end
        total, failed = bucket["total"], bucket["failed"]
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (total, failed)) or not 0 <= failed <= total:
            raise BurnError("request counts must be nonnegative integers with failed <= total")
        cleaned.append({"end": end.isoformat().replace("+00:00", "Z"), "total": total, "failed": failed})
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise BurnError("now must include timezone")
    age = (now.astimezone(timezone.utc) - previous).total_seconds()
    if age < 0 or age > 300:
        raise BurnError("latest bucket is future-dated or stale")
    recent = cleaned[-72:]
    allowance = Decimal("1") - objective

    def window(count: int) -> dict:
        segment = recent[-count:]
        total = sum(item["total"] for item in segment)
        failed = sum(item["failed"] for item in segment)
        burn = Decimal(failed) / Decimal(total) / allowance if total else None
        return {"minutes": count * 5, "total": total, "failed": failed,
                "burn": None if burn is None else str(burn.quantize(Decimal("0.001")))}

    windows = {key: window(count) for key, count in (("5m", 1), ("30m", 6), ("1h", 12), ("6h", 72))}
    def above(key: str, threshold: str) -> bool:
        item = windows[key]
        return bool(item["total"] and Decimal(item["failed"]) >= Decimal(threshold) * Decimal(item["total"]) * allowance)

    fast = above("5m", "14.4") and above("1h", "14.4")
    slow = above("30m", "6") and above("6h", "6")
    digest = hashlib.sha256(json.dumps(recent, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    has_traffic = windows["6h"]["total"] > 0
    return {"service": service, "objective": str(objective), "observed_until": recent[-1]["end"],
            "decision": "PAGE" if fast or slow else ("NO_PAGE" if has_traffic else "INSUFFICIENT_DATA"),
            "fast_burn": fast, "slow_burn": slow,
            "windows": windows, "evidence_sha256": digest,
            "limits": "Synthetic, request-count-based error SLI; no live metrics or latency percentile."}


def assess_segments(data: dict, *, now: datetime | None = None) -> dict:
    """Fail closed when a low-volume payment path is hidden by aggregate health."""
    if not isinstance(data, dict) or set(data) != {"service", "objective", "segments"}:
        raise BurnError("service, objective and segments are required")
    service = data["service"]
    if not isinstance(service, str) or not service.strip() or len(service) > 60:
        raise BurnError("service must be a nonempty bounded name")
    segments = data["segments"]
    if not isinstance(segments, dict) or not 2 <= len(segments) <= 20:
        raise BurnError("2 to 20 named segments are required")
    results = {}
    for name, buckets in sorted(segments.items()):
        if not isinstance(name, str) or not name.strip() or len(name) > 19:
            raise BurnError("segment names must be nonempty and bounded")
        results[name] = assess({"service": f"{service}/{name}", "objective": data["objective"],
                                "buckets": buckets}, now=now)
    paged = [name for name, result in results.items() if result["decision"] == "PAGE"]
    evidence = hashlib.sha256(json.dumps({name: result["evidence_sha256"] for name, result in results.items()},
                                      sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    unknown = [name for name, result in results.items() if result["decision"] == "INSUFFICIENT_DATA"]
    return {"service": service, "decision": "PAGE" if paged else ("INSUFFICIENT_DATA" if unknown else "NO_PAGE"),
            "paged_segments": paged, "segments": results, "evidence_sha256": evidence,
            "limits": "Each synthetic path is evaluated separately; no real payment or production metrics."}
