# 로봇 명령 근거 실습

가상 로봇 명령의 관측 기록을 오프라인에서 검사하는 Python 도구입니다. 고유 요청 ID, 요청·수락·완료 순서, 같은 로봇에 겹친 명령을 확인합니다. 완료 관측이 없으면 성공으로 표시하지 않고 `EVIDENCE_GAP`으로 남깁니다. 명시적으로 관측된 실패는 `FAILED`로 유지합니다. 출력에는 정규화 입력의 SHA-256 해시가 포함됩니다.

```powershell
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -B audit.py samples/commands.json
```

장치와 통신하거나 운영 안전을 인증하지 않으며, 고용주를 위해 수행한 업무를 나타내지 않습니다. 백엔드 API에서 요청 접수증과 실제 실행 근거를 구분하는 방법을 보여주는 가상 실습입니다.
