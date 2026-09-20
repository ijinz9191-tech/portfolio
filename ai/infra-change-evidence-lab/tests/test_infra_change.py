from __future__ import annotations
import json, os, shutil, subprocess, sys, threading, unittest, urllib.error, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from infra_change_evidence.service import create_server
from infra_change_evidence.storage import EvidenceStore
from infra_change_evidence.validator import validate_change

def inventory():
    return {"assets": [
        {"id": "edge-01", "type": "network", "environment": "production", "owner": "infra", "status": "active", "ip": "10.0.0.10", "depends_on": ["dns-01"]},
        {"id": "dns-01", "type": "server", "environment": "production", "owner": "infra", "status": "active", "ip": "10.0.0.53", "depends_on": []},
    ]}

def change():
    return {
        "change_id": "CHG-100", "asset_ids": ["edge-01", "dns-01"], "risk": "medium",
        "window_start": "2026-09-21T01:00:00+09:00", "window_end": "2026-09-21T02:00:00+09:00",
        "steps": ["backup config", "apply and verify"], "rollback_steps": ["restore config", "verify health"],
        "approvers": ["network-lead", "service-owner"], "expected_downtime_minutes": 10,
    }

class ValidatorTests(unittest.TestCase):
    def test_valid_change_is_approved(self):
        self.assertEqual(validate_change(inventory(), change()).status, "APPROVED")
    def test_missing_asset_blocks(self):
        c = change(); c["asset_ids"].append("ghost")
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_duplicate_ip_blocks(self):
        i = inventory(); i["assets"][1]["ip"] = "10.0.0.10"
        self.assertFalse(validate_change(i, change()).checks[1].passed)
    def test_owner_is_required(self):
        i = inventory(); i["assets"][0]["owner"] = ""
        self.assertEqual(validate_change(i, change()).status, "BLOCKED")
    def test_inactive_asset_blocks(self):
        i = inventory(); i["assets"][0]["status"] = "retired"
        self.assertEqual(validate_change(i, change()).status, "BLOCKED")
    def test_dependency_must_be_in_scope(self):
        c = change(); c["asset_ids"] = ["edge-01"]
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_invalid_window_blocks(self):
        c = change(); c["window_end"] = c["window_start"]
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_naive_timestamp_blocks(self):
        c = change(); c["window_start"] = "2026-09-21T01:00:00"
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_long_window_blocks(self):
        c = change(); c["window_end"] = "2026-09-22T02:00:00+09:00"
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_execution_plan_required(self):
        c = change(); c["steps"] = ["only one"]
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_rollback_required(self):
        c = change(); c["rollback_steps"] = []
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_risk_quorum_enforced(self):
        c = change(); c["risk"] = "high"
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_production_downtime_budget(self):
        c = change(); c["expected_downtime_minutes"] = 31
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_emergency_requires_ticket(self):
        c = change(); c.update({"emergency": True, "risk": "high", "approvers": ["a", "b", "c"]})
        self.assertEqual(validate_change(inventory(), c).status, "BLOCKED")
    def test_emergency_with_evidence_passes(self):
        c = change(); c.update({"emergency": True, "emergency_ticket": "INC-9", "risk": "high", "approvers": ["a", "b", "c"]})
        self.assertEqual(validate_change(inventory(), c).status, "APPROVED")
    def test_hash_is_deterministic(self):
        self.assertEqual(validate_change(inventory(), change()).evidence_hash, validate_change(inventory(), change()).evidence_hash)
    def test_bad_inventory_type_raises(self):
        with self.assertRaises(ValueError):
            validate_change({"assets": {}}, change())

class StoreAndApiTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(os.environ.get("TEST_WORK_ROOT", ROOT / "test-work")).resolve()
        self.work.mkdir(parents=True, exist_ok=True)
        for item in self.work.iterdir():
            if item.is_file():
                item.unlink()
        self.store = EvidenceStore(self.work / "evidence.db")
    def tearDown(self):
        for item in self.work.iterdir():
            if item.is_file():
                item.unlink()
    def test_record_get_and_idempotency(self):
        d = validate_change(inventory(), change())
        self.assertEqual(self.store.record(d), "RECORDED")
        self.assertEqual(self.store.record(d), "IDEMPOTENT")
        self.assertEqual(self.store.get("CHG-100")["status"], "APPROVED")
    def test_conflicting_id_rejected(self):
        self.store.record(validate_change(inventory(), change()))
        c = change(); c["expected_downtime_minutes"] = 11
        with self.assertRaises(ValueError):
            self.store.record(validate_change(inventory(), c))
    def test_summary_counts(self):
        self.store.record(validate_change(inventory(), change()))
        c = change(); c["change_id"] = "CHG-101"; c["rollback_steps"] = []
        self.store.record(validate_change(inventory(), c))
        self.assertEqual(self.store.summary(), {"APPROVED": 1, "BLOCKED": 1})
    def test_read_only_http(self):
        self.store.record(validate_change(inventory(), change()))
        server = create_server("127.0.0.1", 0, self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            self.assertEqual(json.load(urllib.request.urlopen(base + "/health"))["status"], "ok")
            self.assertEqual(json.load(urllib.request.urlopen(base + "/decisions/CHG-100"))["status"], "APPROVED")
            req = urllib.request.Request(base + "/summary", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 405)
        finally:
            server.shutdown(); server.server_close(); thread.join()
    def test_cli_approved_and_blocked_exit_codes(self):
        inv = self.work / "inventory.json"
        good = self.work / "good.json"
        bad = self.work / "bad.json"
        inv.write_text(json.dumps(inventory()), encoding="utf-8")
        good.write_text(json.dumps(change()), encoding="utf-8")
        c = change(); c["change_id"] = "CHG-102"; c["rollback_steps"] = []
        bad.write_text(json.dumps(c), encoding="utf-8")
        env = dict(os.environ); env["PYTHONPATH"] = str(ROOT / "src")
        base = [sys.executable, "-m", "infra_change_evidence.cli", "check", "--inventory", str(inv), "--db", str(self.work / "cli.db")]
        self.assertEqual(subprocess.run(base + ["--change", str(good)], env=env, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(base + ["--change", str(bad)], env=env, capture_output=True).returncode, 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
