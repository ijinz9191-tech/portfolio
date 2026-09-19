"""Reproducible synthetic demonstration, never a live analytics claim."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metriclab.store import Store

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-09-20T12:00:00Z"


def demo():
    with tempfile.TemporaryDirectory(prefix="metric-lab-") as directory:
        store = Store(Path(directory) / "metrics.sqlite")
        try:
            for file in sorted((ROOT / "samples/contracts").glob("*.json")):
                store.register(json.loads(file.read_text(encoding="utf-8")), AT)
            initial = store.ingest("sample-initial", json.loads((ROOT / "samples/events.json").read_text()), AT)
            store.materialize("2026-09-19", AT)
            before = store.metrics("2026-09-19", "2026-09-19")
            late = store.ingest("sample-late", json.loads((ROOT / "samples/late-events.json").read_text()), AT)
            stale = store.quality()
            store.materialize("2026-09-19", AT)
            after = store.metrics("2026-09-19", "2026-09-19")
            return {"scenario": "synthetic events with late arrival and rematerialization", "logical_clock": AT,
                    "initial": initial, "before": before, "late": late, "quality_before_rebuild": stale,
                    "after": after, "quality_after_rebuild": store.quality(),
                    "lineage": store.lineage(after[0]["run_id"])}
        finally:
            store.close()


if __name__ == "__main__":
    result = demo()
    body = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/demo-result.json").write_text(body, encoding="utf-8")
    print(body, end="")
