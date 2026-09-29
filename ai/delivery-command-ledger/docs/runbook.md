# 실행 절차

## 검증

1. JDK 21이 PATH에 있는지 확인합니다.
2. 프로젝트 루트에서 `.\verify.ps1`을 실행합니다.
3. 20개 테스트 통과와 종료 코드 0을 확인합니다. 테스트 수가 바뀌면 실제 검증 기록을 기준으로 판단합니다.

## 로컬 API

```powershell
javac --release 21 -d build/classes (Get-ChildItem src/main/java -Recurse -Filter *.java).FullName
java -cp build/classes lab.delivery.DeliveryCommandLedger 8080
```

`GET http://127.0.0.1:8080/health`로 확인합니다. 명령 경로는 POST만 허용합니다.

## 실패 응답

- `400`: 필수 필드·숫자·허용 값 오류
- `404`: 알 수 없는 배송 ID
- `405`: 허용하지 않는 HTTP 메서드
- `409`: 중복 주문, 명령 내용 충돌, 버전 충돌, 잘못된 상태 전이, 수용량 초과

스냅샷을 사용하는 경우 마지막 정상 파일을 별도 보관합니다. 복원 실패 시 새 명령을 받기 전에 파일 무결성을 확인합니다.
