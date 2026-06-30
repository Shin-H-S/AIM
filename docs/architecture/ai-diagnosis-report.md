# AI diagnosis report

AIM의 AI diagnosis report는 `AIDiagnosisInput`에 포함된 결정론적 scan 결과와 evidence를 사용자가 읽을 수 있는 요약으로 바꾸는 출력 계약입니다.

현재 구현된 범위는 `AIDiagnosisReport` Pydantic 스키마 초안입니다. LLM 호출, DB 저장, API 응답 모델, 화면 표시는 아직 포함하지 않습니다.

Report는 다음 정보를 포함합니다.

- report schema version
- input schema version
- project id와 check run id
- 생성 시각
- 짧은 요약
- 결정론적 score/risk 요약
- 우선순위가 있는 top issue
- 개선된 영역
- 회귀한 영역
- generation warning

핵심 제약은 다음과 같습니다.

- `score.deployment_risk`는 `STABLE`, `WARNING`, `RISK` 중 하나여야 합니다.
- `score`는 최소 1개의 evidence id를 참조해야 합니다.
- observation 또는 inference 기반 top issue는 evidence id를 반드시 참조해야 합니다.
- unknown-cause top issue는 원인을 알 수 없는 이유를 포함해야 합니다.
- top issue priority는 중복될 수 없고 낮은 숫자부터 정렬되어야 합니다.
- `WARNING` 또는 `RISK` report는 최소 1개의 top issue를 포함해야 합니다.

이 스키마는 LLM이 authoritative score나 deployment risk를 새로 계산하지 않고, 애플리케이션 로직이 만든 구조화 결과를 설명하도록 제한하기 위한 경계입니다.

후속 작업에서는 `AIDiagnosisInput`을 받아 `AIDiagnosisReport`를 생성하는 서비스 초안을 추가합니다.
