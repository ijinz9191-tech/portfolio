"""Print a synthetic, deterministic SQL plan comparison."""

import json

from .model import reproduce


print(json.dumps(reproduce(), ensure_ascii=False, indent=2))
