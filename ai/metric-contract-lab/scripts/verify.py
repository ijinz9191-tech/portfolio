"""Run real unittest suite and write a small source-bound public report."""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = sorted(p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts)
manifest = [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources]
source_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                        cwd=ROOT, capture_output=True, text=True, timeout=120)
print(result.stdout, end="")
print(result.stderr, end="", file=sys.stderr)
report = {"project": "metric-contract-lab", "checked_at": datetime.now(timezone.utc).isoformat(),
          "python": platform.python_version(), "sqlite": __import__("sqlite3").sqlite_version,
          "platform": platform.system(), "command": "python -B -m unittest discover -s tests -v",
          "exit_code": result.returncode, "status": "PASS" if result.returncode == 0 else "FAIL",
          "source_hash": source_hash, "sources": manifest,
          "scope": "Synthetic local Python/SQLite and loopback HTTP tests; no production workload or deployment",
          "output": (result.stdout + result.stderr)}
(ROOT / "artifacts").mkdir(exist_ok=True)
(ROOT / "artifacts/verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
sys.exit(result.returncode)
