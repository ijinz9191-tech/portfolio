# 공간 네트워크 근거 실습

가상의 이동 네트워크를 오프라인에서 검증합니다. 좌표 범위, 그래프 ID 중복, 존재하지 않는 간선 끝점, 경로 간선의 연결성과 간선별 직선거리 하한을 검사합니다. 정규화 입력의 SHA-256 해시가 출력과 예제를 연결하며 입력 행 순서를 바꾸어도 해시는 같습니다.

```powershell
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -B audit.py samples/network.json
```

가상 지도 점과 경로를 사용해 AI 보조 도구로 만든 포트폴리오 실습입니다. 고용주·고객 위치 자료를 사용하거나 경로를 최적화하지 않습니다. 실제 지도 정확도 또는 과거 GIS 업무를 주장하지 않습니다.
