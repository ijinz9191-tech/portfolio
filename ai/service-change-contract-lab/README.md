# 서비스 변경 계약 영향 실습

여러 서비스가 같은 API를 이용할 때 필드 삭제와 인증 정책 변경이 어느 이용 서비스에 영향을 주는지 확인하는 오프라인 Python 도구입니다. 모든 경로, 이용자, 담당자와 변경 계획은 가상 자료입니다. 실제 LS ITC 시스템이나 고객 서비스와 연결하지 않았습니다.

## 해결하려는 문제

API 변경 자체가 성공해도 기존 이용 서비스가 필수 필드를 읽지 못하면 장애가 발생할 수 있습니다. 이 도구는 변경 전·후 계약과 등록된 이용 서비스의 필요 필드를 대조합니다. 인증된 경로를 공개 경로로 완화하면 항상 `BLOCK`입니다. 영향을 받은 이용자의 확인이 없거나 복구 계획이 비어 있어도 `BLOCK`입니다. 이용자가 확인했고 복구 계획이 있어도 변경은 `REVIEW`이며 사람의 판단이 필요합니다. 등록되지 않은 이용자가 있을 수 있는 삭제 경로도 `REVIEW`로 남깁니다.

## 실행

Python 3.11 이상에서 외부 패키지 없이 실행합니다.

```powershell
conda run -p C:\PRJ\miniconda3 python -B -m unittest discover -s tests -v
conda run -p C:\PRJ\miniconda3 python -B audit.py samples/change.json
```

입력 파일은 `change_id`, 변경 전·후 `route/auth/fields`, 이용 서비스의 `route/fields/owner/acknowledged`, `rollback_plan`을 담습니다. 정상 사례는 필드 추가만 있으므로 `PASS`를 반환합니다. `evidence_sha256`은 입력 순서를 정규화한 자료의 식별값이며 전자 서명이 아닙니다.

## 검증과 한계

정상 추가, 필수 필드 삭제, 이용자 확인·복구 계획, 인증 완화, 미등록 이용자 영향, 잘못된 입력, 입력 순서, 명령행 종료 코드를 테스트합니다. 이 도구는 정적 계약의 일부만 검사합니다. 실제 호출량, 응답 의미, 런타임 오류, 권한 검토 완료나 운영 배포 가능성을 증명하지 않습니다. 사용자가 문제와 검증 기준을 정했고 공개 구현에는 AI 보조 도구를 사용했습니다.

[테스트 코드](tests/test_audit.py)와 [검증 기록](artifacts/verification.json)을 함께 확인할 수 있습니다.
