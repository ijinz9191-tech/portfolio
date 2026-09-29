# 실행 절차

## 검증

```powershell
.\verify.ps1
```

## 가상 예제 확인

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m agent_eval_control_plane.cli demo --db artifacts/demo.sqlite
python -m agent_eval_control_plane.cli gate --db artifacts/demo.sqlite --suite booking-agent-v1
```

## 읽기 전용 보고 서버

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m agent_eval_control_plane.cli serve --db artifacts/demo.sqlite --port 8080
```

제공 경로는 `GET /health`, `GET /runs/<run-id>`, `GET /suites/<suite>/gate`입니다. HTTP 쓰기 요청은 `405`를 반환합니다.

## 복구

실행 ID와 사례 ID는 멱등성을 갖습니다. 같은 ID에 다른 내용을 넣으면 근거를 덮어쓰지 않고 실패합니다. 깨끗한 예제가 필요하면 버릴 수 있는 로컬 데모 DB만 지웁니다. 게시한 검증 메타데이터는 변경하지 않습니다.
