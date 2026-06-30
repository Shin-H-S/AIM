# AI diagnosis report

AIM의 AI diagnosis report는 `AIDiagnosisInput`에 포함된 결정론적 scan 결과와 evidence를 사용자가 읽을 수 있는 요약으로 바꾸는 출력 계약입니다.

현재 구현된 범위는 `AIDiagnosisReport` Pydantic 스키마, `build_ai_diagnosis_report` deterministic generator 서비스, AIReport SQLAlchemy 저장 모델, Alembic 마이그레이션, AIReport 저장 서비스, CheckRun별 AIReport 조회 API, CheckRun 상세 응답의 AIReport 요약 필드입니다. LLM 호출과 화면 표시는 아직 포함하지 않습니다.

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

`ai_reports` 테이블은 다음 정보를 저장합니다.

- CheckRun id
- report schema version
- input schema version
- summary
- overall score
- grade
- deployment risk
- gate reason
- 전체 report JSON payload
- generated/created/updated timestamp

핵심 제약은 다음과 같습니다.

- `score.deployment_risk`는 `STABLE`, `WARNING`, `RISK` 중 하나여야 합니다.
- `score`는 최소 1개의 evidence id를 참조해야 합니다.
- observation 또는 inference 기반 top issue는 evidence id를 반드시 참조해야 합니다.
- unknown-cause top issue는 원인을 알 수 없는 이유를 포함해야 합니다.
- top issue priority는 중복될 수 없고 낮은 숫자부터 정렬되어야 합니다.
- `WARNING` 또는 `RISK` report는 최소 1개의 top issue를 포함해야 합니다.

이 스키마는 LLM이 authoritative score나 deployment risk를 새로 계산하지 않고, 애플리케이션 로직이 만든 구조화 결과를 설명하도록 제한하기 위한 경계입니다.

`aim_api.services.ai_diagnosis_reports.build_ai_diagnosis_report`는 `AIDiagnosisInput`을 받아 다음 방식으로 report를 생성합니다.

- `score_result`를 authoritative score/risk로 사용합니다.
- `score_result` 또는 score evidence가 없으면 report를 생성하지 않습니다.
- risk와 warning statement를 severity 기준으로 정렬해 top issue로 변환합니다.
- comparison delta를 improved area와 regressed area로 분류합니다.
- stable report는 top issue 없이 생성할 수 있습니다.
- warning 또는 risk report에 issue statement가 없으면 score evidence 기반 issue를 생성하고 warning을 남깁니다.

AIReport 저장 모델은 CheckRun당 하나의 report만 저장하도록 `check_run_id`에 unique index를 둡니다. 전체 report는 JSON payload로 보존하되, 목록/상세 조회에서 자주 필요한 score와 deployment risk는 별도 컬럼으로 둡니다.

`aim_api.services.ai_reports.generate_and_record_ai_report`는 CheckRun id를 받아 `AIDiagnosisInput` 생성, deterministic report 생성, `ai_reports` 저장까지 수행합니다. 같은 CheckRun에 report가 이미 있으면 기존 row를 업데이트합니다.

`GET /projects/{project_id}/check-runs/{check_run_id}/ai-report`는 저장된 AIReport를 사용자에게 반환합니다. 이 API는 Bearer token 인증과 프로젝트 소유권 검사를 거치며, 다른 사용자의 프로젝트 또는 CheckRun에 속한 report를 노출하지 않습니다.

`GET /projects/{project_id}/check-runs/{check_run_id}`는 결과 화면 polling에 필요한 compact `ai_report` 요약을 함께 반환합니다. 이 요약에는 `summary`, `overall_score`, `grade`, `deployment_risk`, `gate_reason`, 생성 시각 등 화면 상단에 필요한 필드만 포함하고 전체 `report_json` payload는 포함하지 않습니다.

후속 작업에서는 Worker에서 CheckRun 완료 후 AIReport를 자동 생성·저장하도록 연결합니다.
