# Runbook

## Verification

1. JDK 21이 PATH에 있는지 확인합니다.
2. project root에서 `.\verify.ps1`을 실행합니다.
3. `PASS 18/18`과 exit code 0을 확인합니다.

## Local API

```powershell
javac --release 21 -d build/classes (Get-ChildItem src/main/java -Recurse -Filter *.java).FullName
java -cp build/classes lab.delivery.DeliveryCommandLedger 8080
```

`GET http://127.0.0.1:8080/health`로 확인합니다. Command endpoint는 POST만 허용합니다.

## Failure response

- `400`: required field, number, enum validation
- `404`: unknown delivery
- `405`: wrong HTTP method
- `409`: duplicate order, command payload conflict, version conflict, invalid transition, capacity exceeded

Snapshot을 사용하는 배포에서는 마지막 정상 파일을 별도 보관하고, restore 실패 시 새 명령을 받기 전에 파일 무결성을 확인합니다.
