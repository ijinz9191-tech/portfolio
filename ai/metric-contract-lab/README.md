# 지표 계약 검증 실습

Python·SQLite로 만든 데이터 실습입니다. 버전이 지정된 업무 지표를 정의하고 가상 이벤트를 원자적으로 입력한 뒤 읽기 전용 HTTP API로 일별 값·최신성·데이터 계보를 확인합니다.

## 실행

Python 3.11 이상과 표준 라이브러리만 필요합니다. 이 디렉터리에서 실행합니다.

```sh
python -B scripts/verify.py
python -B scripts/run_demo.py
python -B -m metriclab init
python -B -m metriclab contract samples/contracts/daily_readers.json
python -B -m metriclab contract samples/contracts/daily_reads.json
python -B -m metriclab contract samples/contracts/daily_revenue_cents.json
python -B -m metriclab ingest sample-initial samples/events.json --at 2026-09-20T12:00:00Z
python -B -m metriclab materialize 2026-09-19 --at 2026-09-20T12:00:00Z
python -B -m metriclab serve --port 4192
```

브라우저에서 http://127.0.0.1:4192/metrics?start=2026-09-19&end=2026-09-19 를 열어 확인합니다. 이는 호스팅된 대시보드가 아니라 로컬 JSON API입니다. Ctrl+C로 종료합니다. `--at`은 예제용 고정 시각이며 생략하면 시스템 UTC를 사용합니다.

## 구현한 기능

- 순서가 있는 불변 지표 계약과 허용 목록의 집계 방식 세 가지
- 원자적 입력, 지속 배치 재실행, 이벤트 중복 제거와 충돌 감지
- UTC 일자 경계와 지연 이벤트로 인한 집계 무효화
- 불변 집계 실행 기록, 현재 머리 버전, 입력 집합의 SHA-256 계보
- 읽기 전용 로컬 API·명령행과 실제 SQLite·HTTP·별도 프로세스 테스트

| 가상 지표 | 최초 값 | 지연된 읽기 한 건 추가 후 재집계 |
|---|---:|---:|
| 일별 고유 독자 수 | 2 | 3 |
| 일별 승인된 읽기 수 | 3 | 4 |
| 구매 총액(센트) | 1299 | 1299 |

이 값은 가상 예제 결과이며 운영 업무 지표가 아닙니다. [실행한 데모](artifacts/demo-result.json), [테스트 기록](artifacts/verification.json), [요구사항](docs/requirements.md), [설계](docs/architecture.md), [실행 절차](docs/runbook.md), [검증 범위](docs/verification.md)를 참고하세요. [프로젝트 메타데이터](project.json)는 목록 작성에 사용합니다.

기존 장애 시뮬레이션과 달리 이 구현은 분석 지표 계약, 트랜잭션 입력, 지연 데이터 품질과 지표 계보를 다룹니다.

## 기여와 한계

사용자가 목표와 작업 범위를 제공했습니다. AI 보조 도구로 코드·가상 예제·테스트·문서를 구현했습니다. 사용자가 혼자 작성했거나 고용주 운영 환경에서 실행했다는 뜻이 아닙니다.

외부 LLM·클라우드 서비스·유료 인프라는 사용하지 않습니다. 가상 데이터만 허용하며 구조 검증은 개인정보 분류를 대신하지 않습니다. SQLite 트리거는 애플리케이션 쓰기만 보호하고 DB 소유자를 막지 않습니다. HTTP 서버는 인증이 없으므로 로컬 주소에서만 실행해야 합니다. 운영 SLO·공개 배포·스트리밍 브로커·스케줄러·자율 AI 에이전트 성과를 주장하지 않습니다.

## 구현 깊이와 검증

`Store.materialize`는 한 쓰기 트랜잭션 안에서 이벤트 종류별 입력 개수·고유 사용자 수·금액 합·입력 해시를 한 번 계산한 뒤 여러 계약이 공유하도록 합니다. 캐시는 호출 내부에만 존재하므로 지연 이벤트가 입력된 다음 실행에는 새로운 리비전을 읽습니다. 계약 C개와 선택된 이벤트 N개에 대해 집계 루프는 시간 O(N+C), 추가 공간 O(N)입니다. SQLite 범위 검색·행 정렬·계약 조회 비용은 별도이며 종류별 정렬의 상한은 O(N log N)입니다.

불변조건은 같은 이벤트 종류의 계약이 동일한 입력 집합 해시를 사용하고, 모든 머리 버전 교체가 하나의 트랜잭션으로 성공하거나 함께 되돌아가는 것입니다. `tests/test_depth.py`는 SQLite 추적 콜백으로 33개 계약의 원천 조회가 이벤트 종류 수인 2회인지 확인하고, 다음 트랜잭션에서 추가 이벤트가 새 집계에 반영되는지 검사합니다. 이는 조회 횟수에 대한 구조적 검증이며 처리 시간이나 운영 데이터 처리량의 개선 수치가 아닙니다.
