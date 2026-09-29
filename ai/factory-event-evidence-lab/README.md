# 공장 이벤트 근거 실습

가상의 제조 인계 이벤트를 오프라인에서 검토합니다. 각 제조 단위가 지정된 작업장을 지날 때 `START`와 `COMPLETE`가 순서대로 있는지 확인합니다. 미완료 순서는 `EVIDENCE_GAP`으로 표시하고 작업장 건너뛰기, 중복 이벤트, 불가능한 순서, 모호한 시각은 거부합니다. 결과에 정규화 입력의 SHA-256 해시를 담아 같은 자료를 다시 검토할 수 있습니다.

```powershell
python ai/factory-event-evidence-lab/audit.py ai/factory-event-evidence-lab/samples/events.json
python -m unittest discover -s ai/factory-event-evidence-lab/tests -v
```

예제는 가상으로 만든 기록입니다. MES 연동이나 품질 판정, 특정 제조사에서 수행한 업무를 나타내지 않습니다. 이 검사는 제공된 로그의 정합성만 확인하며 물리적 공정의 실제 수행을 증명하지 않습니다.
