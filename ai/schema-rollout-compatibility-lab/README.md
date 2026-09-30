# 관계형 스키마 순차 배포 호환성 실습

Java 서비스의 구버전·신버전이 동시에 운영될 때 데이터베이스 열 변경으로 읽기, 쓰기, 롤백이 깨지는지 가상 계약으로 검사합니다. 운영 데이터나 회사 내부 스키마를 쓰지 않습니다.

## 실행

```powershell
conda run -p <compatible-environment-prefix> python -B audit.py samples/expand-migrate.json
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
```

입력의 `schemas`는 각 버전의 열, INSERT 때 필요한 열, 기본값이 있는 열을 정의합니다. `apps`는 버전별 읽기·쓰기 열을 정의합니다. `stages`는 단계별 스키마와 동시에 돌 수 있는 앱 버전, 그 시점에 되돌릴 앱 버전을 선언합니다.

검사기는 모든 단계에서 운영 중인 앱과 롤백 앱을 대조합니다. 앱이 읽거나 쓰는 열이 없거나, 기본값 없이 필수인 열을 쓰지 못하면 해당 단계·앱·열을 보고합니다. 단계의 순서를 선언된 그대로 평가하며 근거 해시는 정규화된 입력으로 계산합니다.

샘플은 기존 열을 유지한 채 새 열을 기본값과 함께 확장하고, 두 앱 버전을 혼합 운영한 후 신버전으로 이동합니다. 열을 일찍 삭제하거나 기본값을 없애는 실패 테스트도 포함합니다. 결과가 `PASS`여도 SQL 문법, Oracle·PL/SQL 실행 계획, 데이터 이관, 운영 배포의 안전을 증명하지는 않습니다.
