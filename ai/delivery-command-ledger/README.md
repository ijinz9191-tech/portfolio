# Delivery Command Ledger

공고별 포트폴리오 원칙에 따라 만든 **합성 last-mile delivery backend lab**입니다. 실제 카카오모빌리티 운영 시스템이나 내부 데이터와 무관하며, Java 표준 라이브러리만으로 주문-배송 명령의 일관성과 장애 후 복구를 검증합니다.

## 검증하는 문제

- 같은 명령의 재시도로 중복 배송이 만들어지지 않는가
- 낙관적 버전 충돌과 잘못된 상태 전이가 차단되는가
- courier capacity가 지켜지고 취소 시 즉시 반환되는가
- 명령 결과와 감사 이벤트가 snapshot/restart 뒤에도 보존되는가
- loopback HTTP API가 정상 및 실패 응답을 분리하는가

## 핵심 설계

- 상태: `CREATED → ASSIGNED → PICKED_UP → COMPLETED`, 허용 상태에서 `CANCELLED`
- command ID + payload fingerprint 기반 idempotency
- delivery version 기반 optimistic concurrency control
- courier별 active delivery capacity 검사와 cancel compensation
- append-only audit event sequence
- temp file + atomic move 기반 snapshot
- JDK `HttpServer` 기반 read/write API

## 실행

요구 사항: JDK 21+

```powershell
.\verify.ps1
```

검증 스크립트는 main/test 소스를 새로 컴파일하고 정상·실패·복구·HTTP 경로 18개를 실행합니다.

## 범위와 한계

이 프로젝트는 합성 데이터로 backend consistency 개념을 증명하는 개인 CareerOps 프로젝트입니다. 분산 합의, 실제 결제·배차 연동, 인증, 개인정보, production SLA를 구현했다고 주장하지 않습니다. 실서비스에서는 durable database transaction, outbox, broker, authentication, rate limiting, observability exporter가 추가되어야 합니다.

- [Architecture](docs/architecture.md)
- [Runbook](docs/runbook.md)
- [Verification](docs/verification.md)
