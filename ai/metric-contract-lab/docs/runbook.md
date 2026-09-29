# 실행 절차

이 디렉터리에서 Python 3.11 이상으로 실행하며 pip 설치는 필요하지 않습니다. README의 최초 실행 명령을 따릅니다. 기본 DB는 `.local/metrics.sqlite`입니다. 다른 DB를 쓰려면 하위 명령보다 앞에 `--db`를 둡니다. 부모 디렉터리는 `init`만 생성합니다.

## 지연 자료와 복구

```sh
python -B -m metriclab ingest sample-late samples/late-events.json --at 2026-09-20T12:00:00Z
python -B -m metriclab quality
python -B -m metriclab materialize 2026-09-19 --at 2026-09-20T12:00:00Z
python -B -m metriclab query 2026-09-19 2026-09-19 --metric daily_readers
```

재집계 전 오래된 머리 버전 3개, 이후 0개가 예상됩니다. `daily_readers`는 2에서 3으로 바뀝니다.

| GET 경로 | 결과 |
|---|---|
| /health | 읽기 전용 서비스 상태 |
| /contracts | 모든 계약 버전과 해시 |
| /metrics?start=YYYY-MM-DD&end=YYYY-MM-DD&metric=optional_id | 값·버전·실행 ID·최신성 |
| /quality | 배치·이벤트 수, 중복·지연 이벤트, 오래된 머리 버전 |
| /lineage/positive_run_id | 저장된 실행·정확한 계약·해시·선택 조건 |

Host에는 서버 포트를 포함한 `localhost` 또는 `127.0.0.1`만 허용합니다. 조회 키와 중복을 검사합니다. POST·PUT·PATCH·DELETE는 `405`를 반환합니다. 인증·TLS·공개 서비스 주소·CORS 설정은 없습니다.

## 예외 대응

- `EVENT_ID_CONFLICT`: 가상 원본 자료를 조사하고 이미 승인된 근거를 덮어쓰지 않습니다.
- `BATCH_ID_CONFLICT`: 같은 ID에 다른 내용을 사용했습니다. 실제로 새 배치일 때만 새 ID를 부여합니다.
- `LATE_WINDOW_EXCEEDED`: `--at`은 예제 재실행용이며 실제 지연 이벤트를 숨기는 용도가 아닙니다.
- `STALE`: 영향 날짜를 다시 집계하고 이전 실행 ID를 보존합니다.
- `DATABASE_ERROR` 또는 HTTP `503`: 로컬 디스크·권한·DB 상태를 확인합니다. 마지막 커밋 상태가 복구 지점입니다.
- 정의 수정: 다음 계약 버전을 등록하고 재집계합니다.

Ctrl+C로 종료한 뒤 같은 DB로 다시 시작합니다. 승인된 배치의 재실행은 지속됩니다. `scripts/run_demo.py`는 분리된 임시 디렉터리를 사용하고 정리합니다. 명령행 DB는 의도적으로 유지되므로 자신의 `.local` 파일을 수동으로 지우기 전에 모든 프로세스를 멈춥니다. 운영 데이터나 지원자 자료를 입력하지 않습니다.

백업 서비스, 마이그레이션 엔진, 재시도 스케줄러, 측정된 SLO는 구현하지 않았습니다.
