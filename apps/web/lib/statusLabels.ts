// API enum 원문 → 화면 표시용 한글 라벨.
// 표시 계층 전용이다. 상태 비교·필터 키·payload에는 절대 사용하지 않는다.

// ui.tsx의 checkRunStatusCopy와 표기를 통일한다.
const RUN_STATUS_LABELS: Record<string, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  ANALYZING: "분석 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

const ALERT_STATUS_LABELS: Record<string, string> = {
  PENDING: "대기",
  SENT: "발송됨",
  FAILED: "실패"
};

const ALERT_CHANNEL_LABELS: Record<string, string> = {
  EMAIL: "이메일",
  WEBHOOK: "Webhook"
};

const ALERT_TYPE_LABELS: Record<string, string> = {
  INCIDENT_OPENED: "장애 발생",
  INCIDENT_RECOVERED: "장애 복구",
  DEPLOY_SUMMARY: "배포 요약"
};

const INCIDENT_STATUS_LABELS: Record<string, string> = {
  OPEN: "진행 중",
  RESOLVED: "해소됨"
};

const SEVERITY_LABELS: Record<string, string> = {
  WARNING: "주의",
  RISK: "위험"
};

const DEPLOYMENT_RISK_LABELS: Record<string, string> = {
  STABLE: "안정",
  WARNING: "주의",
  RISK: "위험"
};

const STEP_STATUS_LABELS: Record<string, string> = {
  PASSED: "통과",
  FAILED: "실패",
  SKIPPED: "건너뜀"
};

const TRIGGER_SOURCE_LABELS: Record<string, string> = {
  manual: "수동",
  scheduled: "정기",
  deploy: "배포"
};

const ENVIRONMENT_LABELS: Record<string, string> = {
  development: "개발",
  staging: "스테이징",
  production: "운영"
};

const INCIDENT_TRIGGER_LABELS: Record<string, string> = {
  SERVICE_CONNECTION_FAILURE: "서비스 연결 실패",
  REPEATED_5XX_RESPONSE: "5xx 응답 반복",
  CRITICAL_SCENARIO_FAILURE: "핵심 시나리오 실패",
  PERFORMANCE_SCORE_BELOW_THRESHOLD: "성능 점수 임계값 미달",
  RESPONSE_TIME_ABOVE_THRESHOLD: "응답 시간 임계값 초과",
  DEPLOY_CHECK_COMPLETED: "배포 검사 완료"
};

function labelOrRaw(labels: Record<string, string>, value: string): string {
  return labels[value] ?? value;
}

export function runStatusLabel(status: string): string {
  return labelOrRaw(RUN_STATUS_LABELS, status);
}

export function alertStatusLabel(status: string): string {
  return labelOrRaw(ALERT_STATUS_LABELS, status);
}

export function alertChannelLabel(channel: string): string {
  return labelOrRaw(ALERT_CHANNEL_LABELS, channel);
}

export function alertTypeLabel(alertType: string): string {
  return labelOrRaw(ALERT_TYPE_LABELS, alertType);
}

export function incidentStatusLabel(status: string): string {
  return labelOrRaw(INCIDENT_STATUS_LABELS, status);
}

export function severityLabel(severity: string): string {
  return labelOrRaw(SEVERITY_LABELS, severity);
}

export function deploymentRiskLabel(risk: string): string {
  return labelOrRaw(DEPLOYMENT_RISK_LABELS, risk);
}

export function stepStatusLabel(status: string): string {
  return labelOrRaw(STEP_STATUS_LABELS, status);
}

export function triggerSourceLabel(source: string): string {
  return labelOrRaw(TRIGGER_SOURCE_LABELS, source);
}

export function incidentTriggerLabel(triggerType: string): string {
  return labelOrRaw(INCIDENT_TRIGGER_LABELS, triggerType);
}

export function environmentLabel(environment: string): string {
  return labelOrRaw(ENVIRONMENT_LABELS, environment);
}

export function verifiedLabel(isVerified: boolean): string {
  return isVerified ? "인증됨" : "미인증";
}

export function enabledLabel(enabled: boolean): string {
  return enabled ? "사용 중" : "사용 안 함";
}
