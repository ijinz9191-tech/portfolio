# 실행 절차

1. `verify.ps1`을 실행하고 검사 하나라도 실패하면 게시하지 않습니다.
2. 가상 자료 또는 사용이 승인된 자료로 UTF-8 JSON 자산 목록과 변경 파일을 준비합니다.
3. `src`를 `PYTHONPATH`에 두고 `python -m infra_change_evidence.cli check --inventory inventory.json --change change.json --db evidence.db`를 실행합니다.
4. 종료 코드 `0`은 모든 결정적 검사를 통과했다는 뜻이며 `2`는 변경 차단입니다.
5. 변경 ID를 다른 내용에 다시 쓰면 근거 무결성 오류입니다. 검토 뒤 새 버전 ID를 만듭니다.
6. 근거를 보려면 로컬 인터페이스의 읽기 전용 서비스를 사용합니다. 예제 저장소를 공개하지 않습니다.

이 참고 서비스의 롤백은 내보내기 후 로컬 SQLite 파일을 정리하는 것입니다. 실제 인프라 변경은 수행하지 않습니다.
