"""Run from project root with python -m metriclab."""
import argparse
import sys
import sqlite3
from pathlib import Path
from .api import make_server
from .store import Store, ValidationError, read_json, packed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Synthetic metric contracts, ingestion and lineage")
    parser.add_argument("--db", default=".local/metrics.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    contract = commands.add_parser("contract")
    contract.add_argument("file")
    ingest = commands.add_parser("ingest")
    ingest.add_argument("batch_id")
    ingest.add_argument("file")
    ingest.add_argument("--at", help="Explicit UTC logical clock for reproducible synthetic fixtures")
    materialize = commands.add_parser("materialize")
    materialize.add_argument("day")
    materialize.add_argument("--at")
    query = commands.add_parser("query")
    query.add_argument("start")
    query.add_argument("end")
    query.add_argument("--metric")
    commands.add_parser("quality")
    server = commands.add_parser("serve")
    server.add_argument("--port", type=int, default=4192)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            with make_server(args.db, args.port) as httpd:
                print(packed({"url": f"http://127.0.0.1:{httpd.server_port}", "read_only": True}), flush=True)
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    pass
            return 0
        if args.command == "init":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        elif not Path(args.db).is_file():
            raise ValidationError("DATABASE_NOT_INITIALIZED")
        store = Store(args.db)
        try:
            if args.command == "init":
                result = {"status": "INITIALIZED", "schema": 1}
            elif args.command == "contract":
                result = store.register(read_json(args.file))
            elif args.command == "ingest":
                result = store.ingest(args.batch_id, read_json(args.file), args.at)
            elif args.command == "materialize":
                result = store.materialize(args.day, args.at)
            elif args.command == "query":
                result = {"metrics": store.metrics(args.start, args.end, args.metric)}
            else:
                result = store.quality()
        finally:
            store.close()
        print(packed(result))
        return 0
    except (ValidationError, OSError, sqlite3.Error) as exc:
        print(packed({"error": str(exc) if isinstance(exc, ValidationError) else ("DATABASE_ERROR" if isinstance(exc, sqlite3.Error) else "LOCAL_IO_ERROR")}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
