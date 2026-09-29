# AI 추론 게이트웨이

Java 21 표준 라이브러리로 구현한 로컬 추론 호출 제어 실습입니다. 비동기 요청량 제한, 멱등성, TTL 결과 캐시, 재시도·회로 차단기, 작업 상태 조회와 운영 계수를 다룹니다. 모델은 학습 모델이나 외부 AI API가 아닌 결정적 가상 함수입니다.

## 빌드·검증·실행

JDK 21의 `java`와 `javac`가 PATH에 있어야 하며 근거 생성 스크립트에는 PowerShell 7이 필요합니다. 의존 패키지를 내려받지 않습니다.

```powershell
./verify.ps1
java -cp .build lab.Gateway 4193
```

```sh
curl -i -X POST http://localhost:4193/infer -H "Content-Type: application/x-www-form-urlencoded" -H "Idempotency-Key: demo-001" --data "features=0.2,-0.1,0.7"
curl http://localhost:4193/jobs/REPLACE_WITH_RETURNED_ID
curl http://localhost:4193/metrics
```

반환된 작업 ID를 `SUCCEEDED`, `FAILED`, `CANCELLED` 중 하나가 될 때까지 조회합니다. 종료는 Ctrl+C입니다. 서버는 로컬 주소에만 연결되며 인증, 운영 배포, 브라우저 화면은 없습니다.

## 구현한 동작

- 모델 작업자 하나, 길이가 제한된 대기열, 명시적인 `429` 과부하 응답
- 변경할 수 없는 특성 스냅샷, 멱등성 충돌 감지, 보관 작업 수 제한
- 정규화 특성 지문에 따른 TTL 캐시와 진행 중 요청 보호
- 횟수 제한 재시도, 회로 개방·대기·시험·복구, 정리된 모델 오류
- 진행 작업 정리, 종료 대기 시간 제한, 협조 가능한 작업 취소
- 실제 HTTP 테스트와 통제된 실패 사례

[요구사항](docs/requirements.md), [설계](docs/architecture.md), [실행 절차](docs/runbook.md), [검증 기준](docs/verification.md), [실제 테스트 기록](artifacts/verification.json)을 참고하세요. [프로젝트 메타데이터](project.json)는 포트폴리오 목록에 사용합니다.

## 기여와 한계

사용자가 포트폴리오 목표와 작업 범위를 제공했습니다. AI 보조 도구로 코드·테스트·가상 예제·문서를 구현했습니다. 사용자가 고용주의 운영 시스템을 직접 구현했다는 주장으로 쓰지 않습니다.

상태는 전부 메모리에 있으므로 재시작하면 작업·캐시·계수·멱등 기록이 사라집니다. 재시작 사이에 정확히 한 번 처리됨을 보장하지 않습니다. 실제 모델 학습, 클라우드 GPU, 지속 메시지 브로커, 인증, 분산 조정, 운영 처리량·SLO 성과는 포함하지 않습니다. 가상 특성만 전송해야 합니다.
