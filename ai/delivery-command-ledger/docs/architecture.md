# Architecture

`Service`가 command validation, 상태 전이, optimistic version, courier capacity, event append를 한 synchronized transaction boundary 안에서 처리합니다. command 결과는 payload fingerprint와 함께 저장되어 같은 command 재시도는 기존 결과를 반환하고 다른 payload 재사용은 `409 Conflict`로 차단합니다.

Snapshot은 delivery, order ownership, command result, event sequence를 한 파일로 기록합니다. 임시 파일을 완성한 뒤 atomic replace를 시도하므로 중간 파일이 정상 snapshot을 덮지 않습니다. `Api`는 loopback HTTP만 사용하며 health, delivery query, event query, create/assign/transition command를 제공합니다.

Production 확장 시 in-memory boundary는 RDBMS transaction과 unique constraint로, snapshot은 durable store와 point-in-time recovery로, local event list는 transactional outbox와 broker consumer로 교체할 수 있습니다.
