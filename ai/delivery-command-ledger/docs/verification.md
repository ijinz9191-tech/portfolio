# Verification

`verify.ps1`은 캐시된 class를 삭제하고 Java 21로 전체 소스를 다시 컴파일합니다. 테스트는 다음 범주를 포함합니다.

- 정상: create, assign, pickup, complete, HTTP command/query
- 중복·동시성: idempotent retry, payload conflict, duplicate order, version conflict
- 정책: courier capacity, invalid transition, terminal state
- 보상: cancel 이후 capacity release
- 복구: snapshot round trip, restart 이후 command replay
- API 실패: unknown entity, HTTP method guard

공개 전 최종 소스에서 실행한 결과와 source hash를 `artifacts/verification.txt`에 기록합니다.
