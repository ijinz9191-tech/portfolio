# portfolio

## Incident Replay Lab

Service 간 장애 전파를 재현하고 Runbook의 복구 효과를 확인하는 Backend/SRE 실습 앱입니다. Node.js HTTP API, SQLite, 결정적 Simulation Engine과 Browser Console이 함께 동작합니다.

- **Interactive Topology** — 8개 Service의 의존 관계, Root Fault와 영향 경로를 탐색합니다.
- **Fault Injection** — 4개 Scenario와 Intensity를 선택하고 Run·Pause·Tick으로 시간을 제어합니다.
- **Live Signals** — 서버가 계산한 Latency·Error Rate·Throughput의 변화를 확인합니다.
- **Incident Response** — 원인에 맞는 Runbook을 적용하고 복구 과정과 Timeline을 확인합니다.
- **Replay & Postmortem** — SQLite에 저장된 Snapshot을 재생하고 Postmortem JSON을 내보냅니다.

### Quickstart

Node.js **24 이상**이 필요합니다. 외부 npm Dependency 설치 없이 실행합니다.

```sh
node --version
npm test
npm run build
npm start
```

Browser에서 **http://127.0.0.1:4173**을 엽니다. 서버는 로컬 주소에만 연결되며, 기본 기록은 `data/lab.sqlite`에 저장됩니다.

[실습 순서·Architecture·API·보존 정책 보기](APP.md)

AI 지원으로 구현한 합성 장애 Simulation입니다. 모든 Metric은 모델의 출력이며 실제 고객 Traffic이나 개인의 실무 운영 성과가 아닙니다.
