"""Usage: python -m capacitylab input.json [--now ISO-8601]."""

import argparse
import json
import sys

from .planner import PlanError, _timestamp, plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input file")
    parser.add_argument("--now", help="fixed ISO-8601 time for reproducible replay")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as source:
            result = plan(json.load(source), now=_timestamp(args.now, "now") if args.now else None)
    except (OSError, json.JSONDecodeError, PlanError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
