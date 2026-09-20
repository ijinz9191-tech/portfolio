from __future__ import annotations
import argparse, json
from pathlib import Path
from .service import create_server
from .storage import EvidenceStore
from .validator import validate_change

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate synthetic infrastructure changes")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--inventory", required=True)
    check.add_argument("--change", required=True)
    check.add_argument("--db", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--db", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    if args.command == "check":
        inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8-sig"))
        change = json.loads(Path(args.change).read_text(encoding="utf-8-sig"))
        decision = validate_change(inventory, change)
        state = EvidenceStore(args.db).record(decision)
        print(json.dumps({"record": state, **decision.to_dict()}, ensure_ascii=False, sort_keys=True))
        return 0 if decision.status == "APPROVED" else 2
    server = create_server(args.host, args.port, EvidenceStore(args.db))
    server.serve_forever()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
