"""재현 가능한 합성 SQL 실행 계획 비교 결과를 출력한다."""

import json

from .model import reproduce


print(json.dumps(reproduce(), ensure_ascii=False, indent=2))
