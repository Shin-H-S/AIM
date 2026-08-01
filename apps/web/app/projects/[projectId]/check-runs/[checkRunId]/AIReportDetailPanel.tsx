import { Fragment } from "react";
import {
  type AIReportChange,
  type AIReportDetail,
  type AIReportIssue,
  type LighthouseTopAudit
} from "@/lib/api";
import { Metric } from "@/components/ui";

const statementTypeLabels: Record<AIReportIssue["statement_type"], string> = {
  confirmed_observation: "확인된 관찰",
  evidence_based_inference: "근거 기반 추론",
  unknown_cause: "원인 미확인"
};

const severityLabels: Record<AIReportIssue["severity"], string> = {
  info: "정보",
  warning: "주의",
  risk: "위험"
};

export function AIReportDetailPanel({
  report,
  topAudits
}: {
  report: AIReportDetail;
  topAudits?: LighthouseTopAudit[] | null;
}) {
  const payload = report.report_json;
  // 없음은 한 줄, 문제는 크게 — 이슈·변화·경고가 전부 비면 빈 카드 세 개 대신
  // 요약 한 줄로 끝낸다. 화면 면적은 정보량을 따라간다.
  const allClear =
    payload.top_issues.length === 0 &&
    payload.improved_areas.length === 0 &&
    payload.regressed_areas.length === 0 &&
    payload.generation_warnings.length === 0;

  if (allClear) {
    return (
      <p className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-semibold text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
        ✓ 우선 이슈 · 변화 영역 · 생성 경고 모두 없음 — 안정 상태 리포트입니다.
      </p>
    );
  }

  return (
    <section className="mt-6 grid gap-4">
      <AIReportIssuesList issues={payload.top_issues} topAudits={topAudits ?? null} />

      <section className="grid gap-4 lg:grid-cols-2">
        <AIReportChangesCard changes={payload.improved_areas} title="개선된 영역" />
        <AIReportChangesCard changes={payload.regressed_areas} title="회귀한 영역" />
      </section>

      <AIReportWarningsCard warnings={payload.generation_warnings} />
    </section>
  );
}

function EmptyLine({ label }: { label: string }) {
  return (
    <p className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-400">
      {label} 없음
    </p>
  );
}

function AIReportIssuesList({
  issues,
  topAudits
}: {
  issues: AIReportIssue[];
  topAudits: LighthouseTopAudit[] | null;
}) {
  if (issues.length === 0) {
    return <EmptyLine label="우선 확인 이슈" />;
  }

  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white">우선 확인 이슈</h3>
        <span className="rounded-full bg-cyan-50 dark:bg-cyan-950 px-3 py-1 text-xs font-bold text-cyan-700 dark:text-cyan-400 ring-1 ring-cyan-200 dark:ring-cyan-900">
          {issues.length}개
        </span>
      </div>
      <ul className="grid gap-4">
        {issues.map((issue) => (
          <li className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4" key={issue.id}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-200 dark:bg-slate-700 px-3 py-1 text-xs font-bold text-slate-900 dark:text-white">
                #{issue.priority}
              </span>
              <span
                className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getSeverityBadgeClassName(
                  issue.severity
                )}`}
              >
                {severityLabels[issue.severity]}
              </span>
              <span className="rounded-full bg-cyan-50 dark:bg-cyan-950 px-3 py-1 text-xs font-bold text-cyan-700 dark:text-cyan-400 ring-1 ring-cyan-200 dark:ring-cyan-900">
                {statementTypeLabels[issue.statement_type]}
              </span>
            </div>

            <h4 className="mt-4 text-lg font-semibold text-slate-900 dark:text-white">{issue.title}</h4>
            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{issue.summary}</p>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
                  예상 사용자 영향
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                  {issue.expected_user_impact}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
                  권장 다음 조치
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                  {issue.recommended_next_action}
                </p>
              </div>
            </div>

            {issue.unknown_reason && (
              <p className="mt-4 rounded-2xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950 p-3 text-sm text-amber-800 dark:text-amber-300">
                원인 미확인 이유: {issue.unknown_reason}
              </p>
            )}

            <IssueEvidenceLinks evidenceIds={issue.evidence_ids} topAudits={topAudits} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function AIReportChangesCard({
  changes,
  title
}: {
  changes: AIReportChange[];
  title: string;
}) {
  if (changes.length === 0) {
    return <EmptyLine label={title} />;
  }

  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{title}</h3>
        <span className="rounded-full bg-slate-200 dark:bg-slate-700 px-3 py-1 text-xs font-bold text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-700">
          {changes.length}개
        </span>
      </div>

      <ul className="grid gap-3">
        {changes.map((change) => (
          <li className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4" key={change.id}>
            <p className="text-sm font-semibold text-slate-900 dark:text-white">{change.summary}</p>
            {/* 이전·현재가 없는 변화(요약만 있는 리포트)에 "없음/없음/-1"을 찍지 않는다 —
                값이 있는 항목만 보여준다. */}
            <dl className="mt-3 grid gap-3 text-sm text-slate-600 dark:text-slate-300 sm:grid-cols-3">
              {change.previous_value !== null && (
                <Metric label="이전" value={formatReportValue(change.previous_value)} />
              )}
              {change.current_value !== null && (
                <Metric label="현재" value={formatReportValue(change.current_value)} />
              )}
              {change.delta !== null && (
                <Metric label="변화" value={formatReportValue(change.delta)} />
              )}
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AIReportWarningsCard({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    // 경고 없음은 정상 상태다 — 자리를 차지할 이유가 없다(R2).
    return null;
  }

  return (
    <div className="rounded-2xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950 p-4 text-amber-800 dark:text-amber-300">
      <h3 className="text-lg font-semibold">생성 경고</h3>
      <ul className="mt-3 grid gap-2 text-sm">
        {warnings.map((warning) => (
          <li className="rounded-xl bg-amber-100 dark:bg-amber-950 p-3" key={warning}>
            {warning}
          </li>
        ))}
      </ul>
    </div>
  );
}

function IssueEvidenceLinks({
  evidenceIds,
  topAudits
}: {
  evidenceIds: string[];
  topAudits: LighthouseTopAudit[] | null;
}) {
  const links = resolveEvidenceLinks(evidenceIds, topAudits);
  if (links.length === 0) {
    return null;
  }

  return (
    <p className="mt-4 break-keep text-xs leading-5 text-slate-500 dark:text-slate-400">
      근거:{" "}
      {links.map((link, index) => (
        <Fragment key={`${link.href}-${link.label}`}>
          {index > 0 && " · "}
          <a className="font-semibold text-cyan-700 dark:text-cyan-400 underline" href={link.href}>
            {link.label}
          </a>
        </Fragment>
      ))}
    </p>
  );
}

type EvidenceLink = { label: string; href: string };

function resolveEvidenceLinks(
  evidenceIds: string[],
  topAudits: LighthouseTopAudit[] | null
): EvidenceLink[] {
  const links: EvidenceLink[] = [];
  for (const evidenceId of evidenceIds) {
    const link = resolveEvidenceLink(evidenceId, topAudits);
    if (link && !links.some((existing) => existing.label === link.label)) {
      links.push(link);
    }
  }

  return links;
}

function resolveEvidenceLink(
  evidenceId: string,
  topAudits: LighthouseTopAudit[] | null
): EvidenceLink | null {
  if (evidenceId === "availability-result") {
    return { label: "가용성 검사", href: "#availability-card" };
  }

  if (evidenceId === "ssl-result") {
    return { label: "SSL 검사", href: "#ssl-card" };
  }

  if (evidenceId === "lighthouse-result") {
    return { label: "Lighthouse 결과", href: "#lighthouse-card" };
  }

  if (evidenceId.startsWith("lighthouse-audit-")) {
    const auditId = evidenceId.slice("lighthouse-audit-".length);
    const title = topAudits?.find((audit) => audit.id === auditId)?.title;
    return {
      label: title ? `개선 기회: ${title}` : "Lighthouse 개선 기회",
      href: "#lighthouse-card"
    };
  }

  if (evidenceId === "score-result") {
    return { label: "종합 점수", href: "#score-card" };
  }

  if (evidenceId === "check-run-status") {
    return { label: "검사 실행 상태", href: "#run-status-card" };
  }

  if (evidenceId === "run-comparison") {
    return { label: "직전 run 비교", href: "#comparison-card" };
  }

  if (
    evidenceId.startsWith("scenario-run-") ||
    evidenceId.startsWith("step-result-") ||
    evidenceId.startsWith("console-error-") ||
    evidenceId.startsWith("network-failure-")
  ) {
    return { label: "연결된 ScenarioRun", href: "#scenario-runs-card" };
  }

  return null;
}

function getSeverityBadgeClassName(severity: AIReportIssue["severity"]) {
  if (severity === "risk") {
    return "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900";
  }

  if (severity === "warning") {
    return "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 ring-amber-200 dark:ring-amber-900";
  }

  return "bg-cyan-50 dark:bg-cyan-950 text-cyan-700 dark:text-cyan-400 ring-cyan-200 dark:ring-cyan-900";
}

function formatReportValue(value: string | number | boolean | null) {
  if (value === null) {
    return "없음";
  }

  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }

  return String(value);
}
