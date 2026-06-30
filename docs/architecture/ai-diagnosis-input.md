# AI diagnosis input

AIM의 AI diagnosis는 애플리케이션 로직이 계산한 결정론적 결과를 설명하는 단계입니다. LLM은 authoritative score나 deployment risk를 새로 계산하지 않습니다.

현재 구현된 범위는 `AIDiagnosisInput` Pydantic 스키마와 저장된 scan 결과를 이 스키마로 조립하는 `build_ai_diagnosis_input` 서비스입니다. 이 입력 계약은 다음 데이터를 하나로 묶습니다.

- CheckRun 기본 정보
- availability, SSL, Lighthouse 결과
- 결정론적 score/risk 결과
- 직전 run 비교 결과
- linked ScenarioRun, step result, console error, failed network request
- artifact metadata
- AI에 전달할 evidence item
- confirmed observation, evidence-based inference, unknown cause statement
- generation rule

`aim_api.services.ai_diagnosis_inputs.build_ai_diagnosis_input`은 CheckRun id를 기준으로 availability, SSL, Lighthouse, score, comparison, linked ScenarioRun evidence, artifact metadata를 조회합니다. 이후 LLM에 바로 넘길 수 있는 evidence item과 statement를 생성합니다.

핵심 제약은 다음과 같습니다.

- confirmed observation과 evidence-based inference는 evidence id를 반드시 참조해야 합니다.
- unknown cause statement는 왜 원인을 알 수 없는지 이유를 포함해야 합니다.
- LLM은 제공되지 않은 source code 위치, 내부 로그, 서버 원인을 만들어내면 안 됩니다.
- AI report 생성 실패는 CheckRun 또는 ScenarioRun 성공/실패 상태를 바꾸지 않습니다.

아직 구현되지 않은 범위는 LLM 호출, 사용자에게 보여줄 report API입니다. Report output 스키마와 저장 흐름은 [AI diagnosis report](ai-diagnosis-report.md)에 따로 기록합니다.
