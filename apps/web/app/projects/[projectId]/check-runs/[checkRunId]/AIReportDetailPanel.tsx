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

  return (
    <section className="mt-6 grid gap-5">
      <AIReportIssuesList issues={payload.top_issues} topAudits={topAudits ?? null} />

      <section className="grid gap-4 lg:grid-cols-2">
        <AIReportChangesCard
          changes={payload.improved_areas}
          emptyDescription="이번 리포트에 기록된 개선 영역이 없습니다."
          title="개선된 영역"
        />
        <AIReportChangesCard
          changes={payload.regressed_areas}
          emptyDescription="이번 리포트에 기록된 회귀 영역이 없습니다."
          title="회귀한 영역"
        />
      </section>

      <AIReportWarningsCard warnings={payload.generation_warnings} />
    </section>
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
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-800">
        <h3 className="text-lg font-semibold">우선 이슈 없음</h3>
        <p className="mt-2 text-sm opacity-80">
          AIReport에 top issue가 없습니다. 안정 상태 리포트일 때 정상적으로 발생할 수 있습니다.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900">우선 확인 이슈</h3>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
          {issues.length}개
        </span>
      </div>
      <ul className="grid gap-4">
        {issues.map((issue) => (
          <li className="rounded-2xl border border-slate-200 bg-slate-50 p-4" key={issue.id}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-bold text-slate-900">
                #{issue.priority}
              </span>
              <span
                className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getSeverityBadgeClassName(
                  issue.severity
                )}`}
              >
                {severityLabels[issue.severity]}
              </span>
              <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
                {statementTypeLabels[issue.statement_type]}
              </span>
            </div>

            <h4 className="mt-4 text-lg font-semibold text-slate-900">{issue.title}</h4>
            <p className="mt-2 text-sm leading-6 text-slate-600">{issue.summary}</p>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Expected user impact
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {issue.expected_user_impact}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Recommended next action
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {issue.recommended_next_action}
                </p>
              </div>
            </div>

            {issue.unknown_reason && (
              <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
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
  emptyDescription,
  title
}: {
  changes: AIReportChange[];
  emptyDescription: string;
  title: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
          {changes.length}개
        </span>
      </div>

      {changes.length === 0 ? (
        <p className="text-sm text-slate-500">{emptyDescription}</p>
      ) : (
        <ul className="grid gap-3">
          {changes.map((change) => (
            <li className="rounded-2xl border border-slate-200 bg-slate-50 p-4" key={change.id}>
              <p className="text-sm font-semibold text-slate-900">{change.summary}</p>
              <dl className="mt-3 grid gap-3 text-sm text-slate-600 sm:grid-cols-3">
                <Metric label="Previous" value={formatReportValue(change.previous_value)} />
                <Metric label="Current" value={formatReportValue(change.current_value)} />
                <Metric label="Delta" value={formatReportValue(change.delta)} />
              </dl>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AIReportWarningsCard({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <h3 className="text-lg font-semibold text-slate-900">생성 경고</h3>
        <p className="mt-2 text-sm text-slate-500">기록된 generation warning이 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-800">
      <h3 className="text-lg font-semibold">생성 경고</h3>
      <ul className="mt-3 grid gap-2 text-sm">
        {warnings.map((warning) => (
          <li className="rounded-xl bg-amber-100 p-3" key={warning}>
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
    <p className="mt-4 break-keep text-xs leading-5 text-slate-500">
      근거:{" "}
      {links.map((link, index) => (
        <Fragment key={`${link.href}-${link.label}`}>
          {index > 0 && " · "}
          <a className="font-semibold text-cyan-700 underline" href={link.href}>
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
    return "bg-rose-50 text-rose-700 ring-rose-200";
  }

  if (severity === "warning") {
    return "bg-amber-50 text-amber-700 ring-amber-200";
  }

  return "bg-cyan-50 text-cyan-700 ring-cyan-200";
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
