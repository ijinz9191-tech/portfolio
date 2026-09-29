import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .model import BurnError, assess, assess_segments


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess synthetic multiwindow SLO burn")
    parser.add_argument("input", type=Path)
    parser.add_argument("--now", help="Fixture clock, ISO-8601 with timezone")
    args = parser.parse_args()
    try:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
        data = json.loads(args.input.read_text(encoding="utf-8"))
        result = assess_segments(data, now=now) if "segments" in data else assess(data, now=now)
    except (BurnError, OSError, ValueError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
