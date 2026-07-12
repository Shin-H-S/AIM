import { describe, expect, it } from "vitest";
import {
  alertChannelLabel,
  alertStatusLabel,
  alertTypeLabel,
  deploymentRiskLabel,
  enabledLabel,
  environmentLabel,
  incidentStatusLabel,
  incidentTriggerLabel,
  runStatusLabel,
  scoringPresetLabel,
  severityLabel,
  stepStatusLabel,
  triggerSourceLabel,
  verifiedLabel
} from "./statusLabels";

describe("statusLabels", () => {
  it("maps run statuses to Korean labels", () => {
    expect(runStatusLabel("QUEUED")).toBe("대기 중");
    expect(runStatusLabel("RUNNING")).toBe("실행 중");
    expect(runStatusLabel("ANALYZING")).toBe("분석 중");
    expect(runStatusLabel("COMPLETED")).toBe("완료");
    expect(runStatusLabel("FAILED")).toBe("실패");
    expect(runStatusLabel("CANCELLED")).toBe("취소됨");
  });

  it("maps alert fields to Korean labels", () => {
    expect(alertStatusLabel("PENDING")).toBe("대기");
    expect(alertStatusLabel("SENT")).toBe("발송됨");
    expect(alertChannelLabel("EMAIL")).toBe("이메일");
    expect(alertChannelLabel("WEBHOOK")).toBe("Webhook");
    expect(alertTypeLabel("INCIDENT_OPENED")).toBe("장애 발생");
    expect(alertTypeLabel("INCIDENT_RECOVERED")).toBe("장애 복구");
    expect(alertTypeLabel("DEPLOY_SUMMARY")).toBe("배포 요약");
  });

  it("maps incident fields to Korean labels", () => {
    expect(incidentStatusLabel("OPEN")).toBe("진행 중");
    expect(incidentStatusLabel("RESOLVED")).toBe("해소됨");
    expect(severityLabel("WARNING")).toBe("주의");
    expect(severityLabel("RISK")).toBe("위험");
    expect(incidentTriggerLabel("SERVICE_CONNECTION_FAILURE")).toBe("서비스 연결 실패");
    expect(incidentTriggerLabel("DEPLOY_CHECK_COMPLETED")).toBe("배포 검사 완료");
  });

  it("maps scoring presets to Korean labels", () => {
    expect(scoringPresetLabel("service")).toBe("서비스형");
    expect(scoringPresetLabel("content")).toBe("콘텐츠형");
    expect(scoringPresetLabel("internal")).toBe("내부 도구형");
    expect(scoringPresetLabel("unknown")).toBe("unknown");
  });

  it("maps remaining display enums", () => {
    expect(deploymentRiskLabel("STABLE")).toBe("안정");
    expect(environmentLabel("production")).toBe("운영");
    expect(environmentLabel("development")).toBe("개발");
    expect(stepStatusLabel("SKIPPED")).toBe("건너뜀");
    expect(triggerSourceLabel("manual")).toBe("수동");
    expect(triggerSourceLabel("scheduled")).toBe("정기");
    expect(verifiedLabel(true)).toBe("인증됨");
    expect(enabledLabel(false)).toBe("사용 안 함");
  });

  it("returns unknown values unchanged", () => {
    expect(runStatusLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
    expect(alertChannelLabel("SMS")).toBe("SMS");
    expect(triggerSourceLabel("deploy")).toBe("배포");
  });
});
