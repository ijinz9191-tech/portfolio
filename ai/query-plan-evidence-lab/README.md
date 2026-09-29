# SQL 실행 계획 검증 실습

가상의 테넌트별 업무 대기열 조회를 SQLite로 재현합니다. 4,000개의 합성 데이터를 만들고 `EXPLAIN QUERY PLAN`으로 인덱스 적용 전후의 접근 경로를 기록합니다. 적용하는 인덱스는 `(tenant_id, status, created_at, order_id)`입니다.

## 검증 기준

- 인덱스 적용 전에는 테이블 검색, 적용 후에는 지정한 커버링 인덱스 사용이 실제 실행 계획에 나타나야 합니다.
- 전후 결과 행이 같고, 요청한 테넌트·상태·시간 범위를 벗어난 행이 없어야 합니다.
- `(created_at, order_id)` 순서가 안정적이며 중복 키가 없어야 합니다.
- 다음 20개 행을 가져오는 커서 페이지가 첫 페이지와 겹치거나 경계의 행을 건너뛰지 않아야 합니다.
- 조회문·매개변수·두 페이지의 결과·두 실행 계획을 SHA-256 식별자로 묶습니다.

## 실행과 검증

아래의 환경 경로를 사용 가능한 Conda 환경으로 바꿔 실행합니다.

```powershell
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -B -m planlab
```

테스트에는 결과 변경, 다른 테넌트 또는 상태의 행 유입, 인덱스 누락, 중복 키, 순서 변경, 시간 범위 위반, 커서 페이지 경계 누락 사례가 포함됩니다. 이 자료는 **실행 계획과 결과의 일관성**을 검증합니다. 실제 처리 시간 향상 수치나 근무 회사 시스템의 개선 실적을 뜻하지 않습니다. SQLite 버전에 따라 옵티마이저의 선택은 달라질 수 있습니다.
