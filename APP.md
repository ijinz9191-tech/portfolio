# Incident Replay Lab

합성 장애를 재현하고, 이벤트 수집부터 조치와 복구까지 추적하는 **실행 가능한 Backend/SRE Portfolio 앱**입니다. 정적 자기소개 페이지가 아니라 Node.js HTTP API와 SQLite를 사용하는 작은 로컬 도구입니다.

Source: https://github.com/ijinz9191-tech/portfolio

## 실행

Node.js **24 이상**이 필요합니다. 외부 npm dependency나 계정은 필요하지 않습니다. `node:sqlite`의 experimental warning은 현재 Node 동작에 따른 경고입니다.

```sh
node --version
npm test
npm run build
npm start
```

브라우저에서 **http://127.0.0.1:4173**을 엽니다. 기본 DB는 `data/lab.sqlite`이며 재시작해도 기록이 유지됩니다. 서버를 종료하려면 `Ctrl+C`를 누릅니다. `PORT`와 `LAB_DB` 환경변수로 포트와 DB 위치를 바꿀 수 있습니다.

이 앱은 loopback에만 바인딩합니다. 서버 없이 `index.html`을 열거나 정적 hosting에 `dist`만 올리면 API가 동작하지 않습니다. 외부 배포가 완료됐다고 주장하지 않습니다.

## 2분 사용 흐름

1. **Scenario lab**에서 Query Timeout, Cache Miss, SSO Session Routing 중 하나를 실행합니다.
2. 고유한 Incident와 세 개의 합성 이벤트가 SQLite에 저장됩니다. Inbox에서 선택하거나 제목·ID, Service, 상태로 검색합니다.
3. **조치 적용**을 누르면 `open → mitigating`으로 바뀝니다. **복구 확인**은 조치 후에만 활성화됩니다.
4. 복구 확인 후 `resolved`가 됩니다. Timeline에서 각 이벤트와 UTC timestamp, 수신 sequence를 확인합니다.
5. **중복 재전송**으로 마지막 이벤트를 같은 ID·payload로 다시 보냅니다. 이벤트 수와 상태가 유지되는 것을 확인합니다.
6. 서버를 재시작하고 새로고침하면 저장된 기록이 다시 표시됩니다.

조치와 Probe 결과는 **합성 시나리오 이벤트**입니다. 실제 DB Index, Cache, Network나 외부 Service를 변경·점검하지 않습니다. 카드의 수치는 이 앱 DB의 실제 합성 기록 집계이며 사용자 개인이나 기업 운영 지표가 아닙니다.

## 구조

```text
Browser UI
  │ GET /api/incidents, /api/health
  │ POST /api/scenarios, /api/events, /actions
  ▼
Node HTTP server          src/server.mjs
  ├─ 16 KiB JSON body limit / loopback Host / same-origin writes
  ├─ fixed public asset allowlist
  ▼
Validation + state machine   src/store.mjs
  ▼
SQLite transaction (BEGIN IMMEDIATE)
  ├─ incidents: current aggregate + revision
  └─ events: immutable payload + unique event_id + receipt sequence
```

`src/store.mjs`는 HTTP와 독립적으로 테스트됩니다. 이벤트 추가와 Incident aggregate 변경이 같은 Transaction에 포함되어 Batch 일부가 실패하면 전부 rollback합니다. Prepared statement를 사용하고 검색의 `%`·`_`는 wildcard가 아닌 문자로 취급합니다. DB에는 `foreign_keys`, WAL, 3초 busy timeout을 사용합니다.

### 상태·멱등성 규칙

- 첫 이벤트는 `alert`이며 `open`을 생성합니다.
- `note`는 상태를 유지하고, `mitigation`은 `mitigating`, 이후 `recovery`는 `resolved`로 전이합니다.
- 종료된 Incident는 새 이벤트로 변경할 수 없습니다. 재발은 새 Incident로 기록합니다.
- `eventId`가 같고 정규화된 전체 payload가 같으면 기존 sequence를 반환합니다. 내용이 다르면 HTTP 409입니다.
- 같은 timestamp는 수신 sequence 순서로 처리합니다. 이전 timestamp로 소급하는 late event는 409로 거부합니다. 이는 결정적인 실습 흐름을 위한 의도적 제한이며 분산 시스템의 event-time 재정렬 구현은 아닙니다.
- 한 Batch는 1-20개 이벤트이며 전체가 원자적으로 저장됩니다.
- UI action은 생성형 이벤트를 한 번 요청합니다. 불확실한 네트워크 오류 후 `scenarios`나 `actions`를 자동 재시도하지 않습니다. 원시 이벤트 재전송의 멱등성은 `/api/events`로 검증합니다.

## API

| Method | Path | 입력 / 결과 |
|---|---|---|
| GET | `/api/health` | SQLite readiness, 실제 서버 uptime, synthetic 표시 |
| GET | `/api/scenarios` | 실행 가능한 세 시나리오 |
| POST | `/api/scenarios` | `{"scenario":"checkout-timeout"}`; 생성된 Incident와 세 이벤트 |
| GET | `/api/incidents` | `q`, `status`, `service`, `limit` 필터; 목록, matched, 전체 상태 집계 |
| GET | `/api/incidents/:id` | Incident + 수신 sequence 순서의 전체 Timeline |
| POST | `/api/incidents/:id/actions` | `{"action":"mitigate"}` 또는 `{"action":"recover"}` |
| POST | `/api/events` | `{"events":[...]}`; 각 eventId의 sequence·duplicate 결과 |

```json
{
  "events": [{
    "eventId": "example-event-1",
    "incidentId": "example-incident-1",
    "service": "checkout-api",
    "kind": "alert",
    "message": "Synthetic query timeout",
    "occurredAt": "2026-09-12T00:00:00.000Z"
  }]
}
```

Service는 `checkout-api`, `catalog-api`, `identity-api` 중 하나입니다. Kind는 `alert`, `note`, `mitigation`, `recovery`입니다. 예상하지 않은 필드, 중복 query parameter, 잘못된 UTC 날짜, 80자 초과 검색, 1-100 범위 밖 limit은 거부합니다. 목록은 최신 50건이 기본이며 최대 100건입니다. Pagination·자동 polling·인증·다중 사용자 격리는 이번 범위에 없습니다.

## 검증

`npm test`는 Node 내장 test runner로 실행하며 현재 **16 tests**입니다.

- 실제 ephemeral HTTP server: 시나리오 생성 → 검색 → 조치 → 복구 → 중복 재전송 → Health.
- SQLite 파일 close/reopen 후 Timeline·상태·멱등성 보존.
- 잘못된 상태 전이, eventId 충돌, 원자적 Batch rollback, 시간 역전·Service 변경 거부.
- SQL metacharacter literal 검색과 query 범위 검증.
- 잘못된 JSON, 과대 body, cross-origin 쓰기 및 미허용 파일 접근 거부.
- 공개 Data 계약·개인정보 유출 패턴 거부, 로컬 asset 링크·DOM text rendering 검증.

`npm run build`는 `index.html`, `styles.css`, `app.js`, `public.data.json` 네 파일만 `dist/`로 복사합니다. PDF·DB·Git 파일은 HTTP asset allowlist와 build 양쪽에서 제외됩니다. 테스트 수는 로컬 코드 검사 결과이며 외부 CI나 배포 성공률이 아닙니다.

## 범위와 기여

사용자가 실제 동작하는 Portfolio 앱이라는 목표를 정했고, 이 구현은 AI 지원으로 작성·검증했습니다. 이 저장소를 사용자 단독 작성 Code나 기업 실서비스 구축 성과로 바꾸어 설명하지 않습니다. 모든 시나리오와 이벤트는 명시적인 합성 Data입니다. 원본 이력서 PDF 세 파일과 기존 `README.md`는 그대로 보존했으며 앱에서 읽거나 공개하지 않습니다.

기존 `CAREEROPS.md`는 앞선 정적 Portfolio 단계의 기록입니다. 현재 실행 방법과 제품 범위는 이 문서를 기준으로 확인하세요. 공개 GitHub Source와 Local 실행을 제공하며 외부 배포, 인증된 다중 사용자 운영, 실제 Incident 수집은 구현 범위 밖입니다.
