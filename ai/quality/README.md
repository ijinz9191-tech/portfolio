# 구현 깊이와 검증

32개 실습의 알고리즘 선택, 상태 불변조건, 경계·복구 사례를 현재 소스의 실행 결과와 연결합니다. 각 프로젝트 README에는 변수별 시간·공간 복잡도와 모델의 한계를 기록했습니다.

## 실행 결과

2026-10-02 KST 로컬 검증 기준입니다.

| 대상 | 결과 | 근거 |
| --- | --- | --- |
| 개선 전 32개 프로젝트 | 420개 테스트 통과 | [고정 버전 비교 기록](baseline.json), 커밋 `3ec02b77e736dba0bc61e24adbf97308bfb0ee2c` |
| 개선 후 32개 프로젝트 | 511개 테스트 통과 | [현재 소스·실행 기록](current.json) |
| 검증기 자체 | 10개 테스트 통과 | [실패 판정 반례](../../scripts/tests/test_verify_portfolio.py) |
| 공개 사이트 | 4개 테스트 통과 | [정적 자산·공개 경계](../../site/test.mjs) |

프로젝트 테스트에 HTTP·CLI·임시 SQLite·실제 스레드 병행 실행이 포함됩니다. 개별 요청이나 검증 단언의 수를 테스트 사례 수로 더하지 않습니다. 건너뛰거나 테스트가 없으면 통과하지 않습니다. Java의 개별 PASS 제목에 나온 숫자는 집계에서 제외하고 완전한 종료 요약을 사용합니다. 하위 Python CLI에도 UTF-8 환경을 전달해 Windows 기본 인코딩 차이를 차단합니다.

로컬 Python은 기존 Conda 환경의 **3.11.15**, Node.js는 **24.13.1**, Java는 **21**로 실행했습니다. CI는 Ubuntu에서 세 언어를 새로 준비해 동일한 검사를 수행합니다. 로컬 결과와 CI 결과는 별도 실행 증거입니다. 최종 로컬 기록은 전체 검사에서 통과한 24개 프로젝트의 소스 지문을 재확인하고, 검증기 인코딩·Java 요약 처리를 수정한 후 재실행한 8개 결과를 합산했습니다. 각 항목의 실행 시각과 해당 검사 묶음을 기록에 남겼습니다. CI에서는 현재 커밋의 32개를 모두 실행합니다.

## 무엇을 강화했는가

- **탐색과 인덱스:** 반복 DFS, 역방향 인접 목록, 출발지 공유 Dijkstra, SQL 집계 공유, 키셋 전체 페이지 대조.
- **정확한 계산:** 정수 올림·마이크로초, 정확한 유리수 임계값, 64비트 금액·잔액 경계, 시간 구간 합집합.
- **실행 가능성:** NUMA·PCIe 루트 후보와 펌웨어별 노드 용량을 비교하고 작은 입력을 완전 탐색 기준에 대조.
- **복구와 상태:** 재시도 기한 힙, 원래 명령 응답의 스냅샷 보존, 부분 갱신 롤백, 관측 근거 재사용 차단.

| 프로젝트 | 이번 구현과 반례 | 테스트 |
| --- | --- | --- |
| [Incident Replay Lab](../sre/README.md#구현-깊이와-검증) | **SQLite 저장점·메모리 롤백**. 저장 실패를 주입해 실행 상태와 디스크 상태가 함께 복구되는지 확인합니다. | 31 |
| [Metric Contract Lab](../metric-contract-lab/README.md#구현-깊이와-검증) | **계약별 집계 공유**. 33개 계약의 원천 조회를 이벤트 종류별 2회로 공유하고 다음 실행의 새 입력 반영을 확인합니다. | 35 |
| [AI Inference Gateway](../ai-inference-gateway/README.md#구현-깊이와-검증) | **TTL 최소 힙·병행 멱등성**. 32개 동시 요청의 단일 실행과, 오래된 만료 예약이 갱신 캐시를 삭제하지 않는 조건을 검사합니다. | 14 |
| [Agent Eval Control Plane](../agent-eval-control-plane/README.md#구현-깊이와-검증) | **상충 근거·중복 실행 차단**. 근거 입력 순서를 바꿔도 상충을 차단하고 NaN·무한대 임계값을 거절합니다. | 27 |
| [Infrastructure Change Evidence Lab](../infra-change-evidence-lab/README.md#구현-깊이와-검증) | **전이 의존성 반복 탐색**. 2,000개 자산의 깊은 순환 관계와 미등록 의존성에서 승인 범위의 누락을 검사합니다. | 27 |
| [Delivery Command Ledger](../delivery-command-ledger/README.md#구현-깊이와-검증) | **원래 응답 보존·동시 용량 제한**. 후속 상태 변경·복원 이후에도 원래 명령 응답을 유지하고 20개 동시 배정의 용량 상한을 검사합니다. | 22 |
| [Messenger Reliability Lab](../messenger-reliability-lab/README.md#구현-깊이와-검증) | **기한 힙·활성 메시지 인덱스**. 2,000개 메시지를 전체 스캔 기준과 비교하고 재예약·복원 후 기한과 응답 순서를 검사합니다. | 23 |
| [GPU Topology Reliability Lab](../gpu-topology-reliability-lab/README.md#구현-깊이와-검증) | **PCIe 루트 후보 비교**. 같은 NUMA의 작은 카드 집합을 완전탐색 기준과 비교해 첫 루트 선택 편향을 줄입니다. | 25 |
| [Agentic SDLC Control Plane](../agentic-sdlc-control-plane/README.md#구현-깊이와-검증) | **펌웨어별 실행 가능 배치**. 첫 펌웨어가 불가능해도 다른 버전의 노드 용량을 비교해 조건을 만족하는 예약을 찾습니다. | 23 |
| [Service Mesh Release Safety Lab](../service-mesh-release-safety-lab/README.md#구현-깊이와-검증) | **승격별 새 클러스터 관측**. 클러스터 관측 모드에서 동일 근거 재사용·부분 갱신·시간 역행으로 다음 단계가 승격되지 않게 합니다. | 27 |
| [Kubernetes Capacity Budget Lab](../k8s-capacity-budget-lab/README.md#구현-깊이와-검증) | **정수 올림·최소 용량 탐색**. 2^60+3 복제본의 정확한 올림과 직전 노드 수의 실패를 확인해 최소성을 검증합니다. | 15 |
| [Network Path Triage Lab](../network-path-triage-lab/README.md#구현-깊이와-검증) | **UTC 정규화·근거 경계**. 같은 순간의 다른 시간대 표현, 300초 경계와 301초 거절을 검사합니다. | 11 |
| [SLO Burn Evidence Lab](../slo-burn-evidence-lab/README.md#구현-깊이와-검증) | **누적합·정확한 유리수 비교**. 10^40 요청 수의 임계값 경계를 검사하고 직접 합계 기준과 여러 시간 창의 결과를 대조합니다. | 15 |
| [Query Plan Evidence Lab](../query-plan-evidence-lab/README.md#구현-깊이와-검증) | **전체 키셋 페이지 검증**. 동일 시각·다른 페이지 크기에서 복합 키 순서와 전체 결과의 중복·누락을 검사합니다. | 13 |
| [Incident Dependency Triage Lab](../incident-dependency-triage-lab/README.md#구현-깊이와-검증) | **반복 DFS·역방향 인접 목록**. 1,500개 서비스의 깊은 체인과 순환을 검사하고 고정 난수 DAG를 전이 폐쇄 기준과 대조합니다. | 13 |
| [Tail Latency Attribution Lab](../tail-latency-attribution-lab/README.md#구현-깊이와-검증) | **자식 인덱스·시간 구간 합집합**. 겹친 하위 작업을 중복 차감하지 않고 깊은 추적과 정수 시간축 기준을 비교합니다. | 9 |
| [Delivery Handoff Evidence Lab](../delivery-handoff-evidence-lab/README.md#구현-깊이와-검증) | **인계 상태·실제 관측 간격**. 누락 단계를 추정하지 않고 기한 여유와 실제 인접 관측 간격을 독립 계산과 비교합니다. | 8 |
| [Spatial Network Evidence Lab](../spatial-network-evidence-lab/README.md#구현-깊이와-검증) | **출발지 공유 Dijkstra**. 평행 간선·순환 그래프를 Bellman–Ford 기준과 비교합니다. 최단거리 하한은 필수 경유지를 제외합니다. | 12 |
| [Factory Event Evidence Lab](../factory-event-evidence-lab/README.md#구현-깊이와-검증) | **상태 전이·반개구간 스윕**. 마이크로초 시간과 맞닿은 완료·시작 경계를 검사해 완료된 구간의 동시 lot 수를 계산합니다. | 10 |
| [Robot Command Evidence Lab](../robot-command-evidence-lab/README.md#구현-깊이와-검증) | **명령 구간 충돌·정수 시간**. 1마이크로초 대기와 맞닿은 명령, 시간대가 다른 동일 순간의 처리 결과를 검사합니다. | 10 |
| [Settlement Reconciliation Evidence Lab](../settlement-reconciliation-evidence-lab/README.md#구현-깊이와-검증) | **건별 대조·절대 노출 합계**. 10,000개 정산과 독립 합계를 비교하고 순액이 0이어도 남는 불일치 노출을 확인합니다. | 13 |
| [서비스 변경 계약 영향 실습](../service-change-contract-lab/README.md#구현-깊이와-검증) | **경로 템플릿 충돌 검사**. 변수 이름만 다른 경로의 모호성을 차단하고 HTTP 메서드가 다른 동일 경로는 구분합니다. | 14 |
| [공간 데이터 배포 영향 실습](../spatial-release-impact-lab/README.md#구현-깊이와-검증) | **전후 명세의 역색인**. 삭제된 구간의 기존 영향까지 포함하고 200개 경로 명세를 전체 스캔 기준과 비교합니다. | 11 |
| [계좌 이벤트 순서·멱등 재생 실습](../account-event-replay-lab/README.md#구현-깊이와-검증) | **멱등 재생·64비트 잔액**. 20,000개 역순 이벤트와 재전송을 독립 누적 기준에 대조하고 중간 잔액 오버플로를 검사합니다. | 13 |
| [가상 이체 기장 완결성 검사](../transfer-posting-evidence-lab/README.md#구현-깊이와-검증) | **기장 쌍·잔액 보존**. 대상 계좌 오버플로에서 출금도 적용되지 않는지 확인하고 합계 보존과 잔액 범위를 검사합니다. | 12 |
| [답변 근거 추적 실습](../grounded-answer-evidence-lab/README.md#구현-깊이와-검증) | **문서 정규화·해시 공유**. 1,000개 주장의 문서 재사용을 확인하고 공백 차이만 있는 중복 인용을 검출합니다. | 9 |
| [결제 시도·제공자 응답 근거 실습](../payment-attempt-evidence-lab/README.md#구현-깊이와-검증) | **요청·제공자 상태 대조**. ACK와 거절 근거의 상충을 확인하고 금액·멱등 키가 불일치하면 접근 후보를 차단합니다. | 16 |
| [상품 변경 안전 검토 실습](../merchandising-change-safety-lab/README.md#구현-깊이와-검증) | **버전 검사·정수 노출 계산**. 가격×재고 변화의 독립 계산과 stale 버전 차단을 확인해 검토 결과와 적용 후보를 구분합니다. | 10 |
| [구독 접근권·제휴사 확인 대조 실습](../subscription-entitlement-reconciliation-lab/README.md#구현-깊이와-검증) | **결제 ID의 소유 기간 검사**. 다른 구독·기간의 결제 ID 재사용과 잘못된 연도·유니코드 기간을 거절합니다. | 11 |
| [PG 인증 귀환·서버 확인 대조 실습](../pg-auth-return-integrity-lab/README.md#구현-깊이와-검증) | **nonce 재사용·순열 검증**. 다른 주문에 재사용한 nonce를 거절하고 입력 순서가 달라도 같은 근거 해시인지 확인합니다. | 10 |
| [관계형 스키마 순차 배포 호환성 실습](../schema-rollout-compatibility-lab/README.md#구현-깊이와-검증) | **스키마·앱 쌍 메모이제이션**. 1,000개 단계에서 같은 계약은 한 번 계산하면서 단계별 2,000개 실패 근거는 보존합니다. | 9 |
| [가상 이체 트랜잭션·발행 대기 복구 실습](../transactional-outbox-recovery-lab/README.md#구현-깊이와-검증) | **inbox·기장의 원자적 복구**. 두 번째 계좌 갱신 실패에서 첫 갱신과 inbox가 함께 롤백되고 ACK가 남지 않는지 확인합니다. | 13 |

## 재현 방법

Python 3.11 이상, Node.js 24, JDK 21을 준비합니다. Python 프로젝트 검사에는 외부 패키지가 필요하지 않습니다. Conda를 사용한다면 본인의 격리된 환경을 선택해 실행합니다.

```powershell
conda run -n <환경이름> --no-capture-output python -X utf8 scripts/verify_portfolio.py --report .tooling/local-quality.json
conda run -n <환경이름> --no-capture-output python -X utf8 -m unittest discover -s scripts/tests -v
npm ci --ignore-scripts
npm test
npm run format:check
```

Java가 PATH에 없으면 `--java <java 실행파일> --javac <javac 실행파일>`을 지정합니다. 특정 실습만 확인할 때는 `--projects <프로젝트 ID>`를 사용합니다. 고정 버전 비교 시에는 해당 커밋의 `ai/` 디렉터리를 별도 경로에 펼친 후 `--root <비교 경로>`를 지정합니다. [목록](projects.json)은 중복 없는 32개 프로젝트를 검사합니다.

[검증기](../../scripts/verify_portfolio.py)는 각 실습을 독립 프로세스에서 실행하고 종료 코드·실패·건너뜀·소스 지문을 기록합니다. Java는 매 소스 지문마다 별도 빌드 경로에서 다시 컴파일합니다. 검사 시작과 끝의 소스가 다르면 실패합니다. 소스 지문은 상대 경로와 LF로 정규화한 내용을 사용하며 생성물·DB·캐시는 제외합니다.

## 유지보수 기준

소스를 저장할 때 JS·HTML·CSS·JSON·YAML은 Prettier 3.9.9, Python은 Ruff 0.16.8, Java는 google-java-format 1.36.0으로 포맷합니다. Markdown은 별도로 읽고 검토합니다. 포맷터의 버전과 Java JAR SHA-256은 [배포 워크플로](../../.github/workflows/pages.yml)에 고정했습니다. 32개 검사와 공개 자산 검증이 실패하면 Pages 배포가 진행되지 않습니다.

복잡도 설명에서 정렬·직렬화·큰 정수의 비트 연산·출력 크기·DB와 파일 I/O 비용을 구분합니다. 기준 구현 대조에는 고정 난수와 작은 완전 탐색을 사용합니다. 테스트 개수 증가는 커버리지 비율이나 성능 향상 배율을 뜻하지 않습니다.

## 적용 범위

모든 자료는 합성 입력을 사용한 로컬 실습입니다. 공인 프로그래머스 레벨, 실제 회사 운영 성과, 금융·보안 인증, 분산 exactly-once를 주장하지 않습니다. 시간 복잡도와 불변조건을 설명할 수 있고 반례를 재현할 수 있는 구현을 제공하는 것이 이 기록의 기준입니다. 실제 서비스 연결·성능 측정·영속성 보장은 프로젝트별로 추가 검증해야 합니다.
