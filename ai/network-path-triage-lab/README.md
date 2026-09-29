# 네트워크 경로 진단 실습

가상의 Kubernetes 서비스 요청을 오프라인에서 검토하는 작은 진단 모델입니다. DNS, Service 선택, EndpointSlice, NetworkPolicy, 서비스 메시, 애플리케이션을 순서 있는 경로로 다룹니다. 앞선 탐침이 모두 최신이고 확인됐을 때 첫 실패 탐침을 원인 **후보**로 제시합니다. 이후 실패는 증상으로 남기며 앞단 탐침이 미확인이면 확정적인 진단을 하지 않습니다.

```powershell
python -B triage.py samples/network-policy.json --now 2026-09-29T04:00:00Z
$env:PYTHONPATH='.'
python -B -m unittest discover -s tests -v
```

예제는 `policy`를 조사 후보로 표시하고 출발지·목적지 정책 점검을 제안하며 결정적인 SHA-256 근거 ID를 남깁니다. 모든 관측에는 시각이 필요하고 기본 허용 경과 시간은 5분입니다. 도구는 소켓을 열거나 클러스터를 읽지 않으므로 운영 장애의 원인을 증명할 수 없습니다.

## 출처

DevOps 지원을 위해 AI 보조 도구로 만든 가상 포트폴리오 자료입니다. 지원자의 기존 배포 운영·모니터링·DMZ 전환 지원과 새 실습 구현은 구분합니다. 고용주 네트워크 세부 정보나 자격 증명은 포함하지 않습니다.
